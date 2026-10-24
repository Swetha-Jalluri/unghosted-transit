"""Run-command guard for the documented delivery layer (R11.8).

Requirement 11.8: the App, the API, the MCP_Server and the tests are run
through ``uv``, such that every documented run command begins with ``uv run``
and none invokes ``pip`` or a ``requirements.txt`` file.

This test scans two documentation surfaces:

1. ``README.md`` at the repo root -- the human-facing run instructions.
2. The About and API & MCP Streamlit pages (``app/about.py`` and
   ``app/api_mcp.py``) -- any command strings baked into the page source.

For each surface it collects the lines/string literals that *look like* a run
command (they invoke one of the known tools: ``streamlit``, ``uvicorn``,
``pytest``, ``python -m``, ``python <script>``, or the mcp server module) and
asserts that command is prefixed with ``uv run``. Prose that merely mentions a
tool name without being an actual invocation is ignored, to avoid false
positives. Each surface is also checked for any ``pip`` invocation or
``requirements.txt`` reference.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
ABOUT = REPO_ROOT / "app" / "about.py"
API_MCP = REPO_ROOT / "app" / "api_mcp.py"

# The tools whose invocation counts as a "run command". A line/string is only
# treated as a command when it actually invokes one of these -- a bare mention
# of the word in prose does not count.
#
# Each entry is a regex matched against the *start* of the candidate command
# token sequence (after stripping any leading "uv run " prefix and a leading
# "$ " shell prompt). Anchored with \b so "pytestify" would not match.
_TOOL_PATTERNS = (
    r"streamlit\b",
    r"uvicorn\b",
    r"pytest\b",
    r"python\s+-m\b",
    r"python\s+scripts/",
    r"python3\s+-m\b",
    r"python3\s+scripts/",
)
_TOOL_RE = re.compile(r"(?:" + "|".join(_TOOL_PATTERNS) + r")")

# A leading "uv run " (optionally with a shell prompt or flags) prefix.
_UV_RUN_RE = re.compile(r"^uv\s+run\b")

# A shell prompt that may precede a command in docs, e.g. "$ uv run ...".
_PROMPT_RE = re.compile(r"^\s*\$\s*")

# A pip *invocation* -- "pip" (or "pip3"/"python -m pip") followed by a
# subcommand such as install/uninstall/freeze/list. This distinguishes an
# actual command from prose that merely says we do not use pip.
_PIP_RE = re.compile(
    r"(?<![\w-])(?:python3?\s+-m\s+)?pip3?\s+"
    r"(install|uninstall|freeze|list|download|wheel|config)\b",
    re.IGNORECASE,
)
_REQUIREMENTS_RE = re.compile(r"requirements\.txt", re.IGNORECASE)


def _normalize(command: str) -> str:
    """Strip a shell prompt and surrounding whitespace from a command line."""
    return _PROMPT_RE.sub("", command).strip()


def _looks_like_run_command(text: str) -> bool:
    """True when ``text`` invokes one of the known run tools.

    The tool token must appear at the start of the command, either directly or
    immediately after a ``uv run`` prefix. This keeps the heuristic from firing
    on prose like "the pytest suite" where the word is mid-sentence.
    """
    stripped = _normalize(text)
    # Peel an optional "uv run " prefix before looking for the tool token.
    after_uv = _UV_RUN_RE.sub("", stripped).strip()
    candidate = after_uv if after_uv != stripped else stripped
    return bool(_TOOL_RE.match(candidate))


def _requires_uv_run(text: str) -> bool:
    """True when a run command is NOT prefixed with ``uv run``."""
    stripped = _normalize(text)
    return not _UV_RUN_RE.match(stripped)


# ---------------------------------------------------------------------------
# README.md scanning
# ---------------------------------------------------------------------------
def _readme_text() -> str:
    assert README.exists(), f"README.md not found at {README}"
    return README.read_text(encoding="utf-8")


def _readme_candidate_lines(text: str) -> list[str]:
    """Return candidate command lines from README.

    Scans both fenced code blocks and ordinary lines. Within a fenced block the
    language tag (e.g. ```json) is tracked so JSON/response examples are not
    mistaken for commands. Only lines that look like a run command are
    returned.
    """
    candidates: list[str] = []
    in_fence = False
    fence_lang = ""
    for raw in text.splitlines():
        fence = raw.strip()
        if fence.startswith("```"):
            if not in_fence:
                in_fence = True
                fence_lang = fence[3:].strip().lower()
            else:
                in_fence = False
                fence_lang = ""
            continue

        # Skip the body of non-shell fenced blocks (json, text, http, ...).
        if in_fence and fence_lang in {"json", "text", "http", "yaml", "toml"}:
            continue

        line = raw.strip()
        if not line:
            continue
        # Inline code spans in prose: pull out `...` fragments too, so a command
        # documented inline (e.g. run `uv run pytest -q`) is still checked.
        for span in re.findall(r"`([^`]+)`", line):
            if _looks_like_run_command(span):
                candidates.append(span)
        if _looks_like_run_command(line):
            candidates.append(line)
    return candidates


def test_readme_run_commands_use_uv_run():
    # Feature: unghosted-demo, R11.8 -- every documented run command uses uv run.
    text = _readme_text()
    offenders = [
        cmd for cmd in _readme_candidate_lines(text) if _requires_uv_run(cmd)
    ]
    assert not offenders, (
        "Every run command in README.md must begin with `uv run`; found "
        f"commands without it: {offenders}"
    )


def test_readme_has_no_pip_or_requirements():
    # Feature: unghosted-demo, R11.8 -- no pip, no requirements.txt.
    text = _readme_text()
    pip_hits = _PIP_RE.findall(text)
    req_hits = _REQUIREMENTS_RE.findall(text)
    assert not pip_hits, f"README.md must not invoke pip: found {pip_hits}"
    assert not req_hits, (
        f"README.md must not reference requirements.txt: found {req_hits}"
    )


# ---------------------------------------------------------------------------
# About / API & MCP page scanning
# ---------------------------------------------------------------------------
def _string_constants(path: Path) -> list[str]:
    """Every string literal in a Python source file (docstrings included)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
    return out


def _page_candidate_commands(path: Path) -> list[str]:
    """Return run-command-looking fragments from a page's string literals.

    A page string may be a whole paragraph, so each literal is split into lines
    and inline `code spans`, and only the fragments that look like a run command
    are returned.
    """
    candidates: list[str] = []
    for literal in _string_constants(path):
        for line in literal.splitlines():
            line = line.strip()
            if not line:
                continue
            for span in re.findall(r"`([^`]+)`", line):
                if _looks_like_run_command(span):
                    candidates.append(span)
            if _looks_like_run_command(line):
                candidates.append(line)
    return candidates


def test_page_run_commands_use_uv_run():
    # Feature: unghosted-demo, R11.8 -- page-documented commands use uv run.
    offenders: dict[str, list[str]] = {}
    for path in (ABOUT, API_MCP):
        assert path.exists(), f"expected page source at {path}"
        bad = [
            cmd for cmd in _page_candidate_commands(path) if _requires_uv_run(cmd)
        ]
        if bad:
            offenders[path.name] = bad
    assert not offenders, (
        "Run commands documented on the About / API & MCP pages must begin "
        f"with `uv run`; found commands without it: {offenders}"
    )


def test_pages_have_no_pip_or_requirements():
    # Feature: unghosted-demo, R11.8 -- no pip, no requirements.txt on pages.
    offenders: dict[str, list[str]] = {}
    for path in (ABOUT, API_MCP):
        text = path.read_text(encoding="utf-8")
        hits: list[str] = []
        hits.extend(_PIP_RE.findall(text))
        hits.extend(_REQUIREMENTS_RE.findall(text))
        if hits:
            offenders[path.name] = hits
    assert not offenders, (
        "The About / API & MCP pages must not invoke pip or reference "
        f"requirements.txt: {offenders}"
    )
