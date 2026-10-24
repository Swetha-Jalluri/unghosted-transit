"""Boundary and no-hardcoding guards for the delivery layer.

A single static scan of the four delivery roots -- ``streamlit_app.py`` and the
packages ``app/``, ``api/`` and ``mcp_server/`` -- enforces the branch contract:

1. R11.1 Import boundary: the only ``core`` modules the delivery layer may
   import are ``core.service`` and ``core.contracts``. Any ``import core...`` or
   ``from core... import`` of another submodule is a violation.

2. R11.5 No hardcoding: every URL, route path, demo stop/station id and
   coordinate must come through Settings (``app/settings.py``), so no other
   scanned source file may contain those as string/number literals. The scan
   operates on AST constants (so comments and code structure are ignored) and
   excludes ``app/settings.py``, which is the single source allowed to hold
   them.

3. R7.6 No logos: no MBTA or Bluebikes logo/brand asset is referenced from the
   scanned source.

4. R11.7 Secrets: ``.env`` is never tracked by git (``.env.example`` is fine).

The test scans source only (not ``tests/``) and reads the demo ids from the
Service at run time, so it stays accurate if the fixtures change.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

import core.service as core_service

# ---------------------------------------------------------------------------
# Scan set: the four delivery roots named by R11.1 / R11.5.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]

# app/settings.py is the single source allowed to hold URLs, routes and the
# like, so it is excluded from the no-hardcoding scan (but NOT from the import
# scan -- it is still only allowed to import core.service / core.contracts).
SETTINGS_FILE = (REPO_ROOT / "app" / "settings.py").resolve()


def _scanned_files() -> list[Path]:
    """Return every ``.py`` file under the four delivery roots.

    ``streamlit_app.py`` plus everything recursively under ``app/``, ``api/``
    and ``mcp_server/``. ``__pycache__`` is skipped. ``scripts/`` is NOT part of
    the scan set (the one-time fetch script lives outside these four roots).
    """
    files: list[Path] = []

    entry = REPO_ROOT / "streamlit_app.py"
    if entry.exists():
        files.append(entry.resolve())

    for package in ("app", "api", "mcp_server"):
        root = REPO_ROOT / package
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            files.append(path.resolve())

    return sorted(set(files))


def _rel(path: Path) -> str:
    """Repo-relative, forward-slash path for readable assertion messages."""
    return path.relative_to(REPO_ROOT).as_posix()


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _string_constants(tree: ast.Module) -> list[str]:
    """Every string literal (``ast.Constant`` of ``str``) in the tree.

    Docstrings are ``ast.Constant`` nodes too and are included; the heuristics
    below are chosen so legitimate prose does not trip them.
    """
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
    return out


def _number_constants(tree: ast.Module) -> list[float]:
    """Every int/float literal in the tree (booleans excluded)."""
    out: list[float] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if isinstance(node.value, bool):
                continue
            out.append(float(node.value))
    return out


# ---------------------------------------------------------------------------
# Demo ids come from the Service, not from a hardcoded list here, so the guard
# tracks whatever the fixtures actually expose.
# ---------------------------------------------------------------------------
def _demo_stop_ids() -> set[str]:
    return {stop.stop_id for stop in core_service.list_demo_stops()}


def _demo_station_ids() -> set[str]:
    # get_nearby_docks returns every demo dock regardless of the coordinates
    # passed, so (0, 0) with a generous limit enumerates the station ids.
    docks = core_service.get_nearby_docks(0.0, 0.0, walk_min=30, limit=1000, mode="demo")
    return {dock.station_id for dock in docks}


# ===========================================================================
# R11.1 -- import boundary.
# ===========================================================================
_ALLOWED_CORE_MODULES = {"core.service", "core.contracts"}


def _core_imports(tree: ast.Module) -> list[str]:
    """Return every imported ``core`` module name that is not allowed.

    Handles both ``import core.x`` / ``import core.x as y`` and
    ``from core.x import ...`` / ``from core import ...``. Only ``core.service``
    and ``core.contracts`` are permitted; bare ``import core`` or any other
    ``core`` submodule counts as a violation.
    """
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name == "core" or name.startswith("core."):
                    if name not in _ALLOWED_CORE_MODULES:
                        bad.append(name)
        elif isinstance(node, ast.ImportFrom):
            # Only absolute imports have a module; relative (level>0) can't be
            # core from the delivery layer.
            module = node.module or ""
            if node.level == 0 and (module == "core" or module.startswith("core.")):
                if module == "core":
                    # from core import service  -> allowed only if every name
                    # imported is service/contracts.
                    for alias in node.names:
                        if alias.name not in {"service", "contracts"}:
                            bad.append(f"core.{alias.name}")
                elif module not in _ALLOWED_CORE_MODULES:
                    bad.append(module)
    return bad


def test_delivery_imports_only_core_service_and_contracts():
    # Feature: unghosted-demo, R11.1 import boundary
    violations: dict[str, list[str]] = {}
    for path in _scanned_files():
        bad = _core_imports(_parse(path))
        if bad:
            violations[_rel(path)] = sorted(set(bad))
    assert not violations, (
        "Delivery layer may only import core.service / core.contracts; found "
        f"other core imports: {violations}"
    )


def test_scan_set_is_non_empty():
    # A guard on the guard: if the scan set were empty the import/hardcoding
    # tests would pass vacuously, which would hide real regressions.
    assert _scanned_files(), "no delivery source files were found to scan"


# ===========================================================================
# R11.5 -- no hardcoded URLs, routes, ids or coordinates outside settings.py.
# ===========================================================================
_URL_RE = re.compile(r"https?://")
_ROUTE_RE = re.compile(r"/v1/")

# R11.5 governs data-source and API URLs (they must come from Settings). A font
# or stylesheet CDN referenced from a CSS block is a presentation asset, not a
# data URL, so those hosts are allow-listed to keep the guard from firing on
# legitimate styling. Add a host here only when it is purely cosmetic.
_STYLE_URL_HOSTS = (
    "fonts.googleapis.com",
    "fonts.gstatic.com",
)
# A URL that appears inside a CSS url(...) reference (e.g. @import url('...'))
# is likewise a stylesheet asset, not a data URL.
_CSS_URL_RE = re.compile(r"url\(\s*['\"]?https?://", re.IGNORECASE)


def _hardcoding_files() -> list[Path]:
    """Scanned files minus ``app/settings.py`` (the allowed single source)."""
    return [p for p in _scanned_files() if p != SETTINGS_FILE]


def _data_urls_in(literal: str) -> list[str]:
    """Return the data/API URLs in ``literal``, ignoring stylesheet assets.

    Each ``http(s)://`` occurrence is examined: it is ignored when it points at
    an allow-listed font/style CDN or sits inside a CSS ``url(...)`` reference,
    and reported otherwise.
    """
    hits: list[str] = []
    for match in _URL_RE.finditer(literal):
        start = match.start()
        # The host is the run of URL characters right after the scheme.
        tail = literal[start:]
        host_match = re.match(r"https?://([^/\s'\"\)]+)", tail)
        host = host_match.group(1).lower() if host_match else ""
        if any(host == h or host.endswith("." + h) for h in _STYLE_URL_HOSTS):
            continue
        # Is this occurrence wrapped in a CSS url(...) call?
        prefix = literal[max(0, start - 6):start + 1]
        if _CSS_URL_RE.search(literal[max(0, start - 6):match.end()]) or prefix.lower().rstrip().endswith("url("):
            continue
        hits.append(host or tail[:40])
    return hits


def test_no_hardcoded_urls_outside_settings():
    # Feature: unghosted-demo, R11.5 -- data/API URLs come from Settings only.
    violations: dict[str, list[str]] = {}
    for path in _hardcoding_files():
        hits: list[str] = []
        for literal in _string_constants(_parse(path)):
            hits.extend(_data_urls_in(literal))
        if hits:
            violations[_rel(path)] = sorted(set(hits))
    assert not violations, (
        "Data/API URLs must come from Settings, not string literals "
        f"(font/stylesheet CDNs are allowed): {violations}"
    )


def test_no_hardcoded_v1_routes_outside_settings():
    # Feature: unghosted-demo, R11.5 -- /v1 route paths come from Settings only.
    violations: dict[str, list[str]] = {}
    for path in _hardcoding_files():
        hits = [s for s in _string_constants(_parse(path)) if _ROUTE_RE.search(s)]
        if hits:
            violations[_rel(path)] = sorted(set(hits))
    assert not violations, (
        "/v1 route paths must come from Settings, not string literals: "
        f"{violations}"
    )


def test_no_hardcoded_demo_ids_outside_settings():
    # Feature: unghosted-demo, R11.5 -- stop/station ids come from the Service.
    demo_ids = _demo_stop_ids() | _demo_station_ids()
    assert demo_ids, "expected the Service to expose at least one demo id"

    violations: dict[str, list[str]] = {}
    for path in _hardcoding_files():
        found = set()
        for literal in _string_constants(_parse(path)):
            for demo_id in demo_ids:
                # A demo id must not appear anywhere inside a string literal
                # (exact match or embedded, e.g. "stop=place-haecl").
                if demo_id in literal:
                    found.add(demo_id)
        if found:
            violations[_rel(path)] = sorted(found)
    assert not violations, (
        "Demo stop/station ids must come from list_demo_stops()/the Service, "
        f"not string literals: {violations}"
    )


def test_no_hardcoded_coordinates_outside_settings():
    # Feature: unghosted-demo, R11.5 -- coordinates come from Settings only.
    #
    # Pragmatic heuristic: a coordinate-looking literal is a non-integer float
    # in the Boston-area ranges (latitude ~42.x, longitude ~-71.x). This flags
    # a pasted lat/lon while leaving ordinary numbers (limits, step seconds,
    # percentages) alone to avoid false positives.
    def _looks_like_coord(value: float) -> bool:
        if value == int(value):
            return False  # whole numbers are not coordinates here
        in_lat_band = 41.0 <= value <= 43.0
        in_lon_band = -72.0 <= value <= -70.0
        return in_lat_band or in_lon_band

    violations: dict[str, list[float]] = {}
    for path in _hardcoding_files():
        hits = [n for n in _number_constants(_parse(path)) if _looks_like_coord(n)]
        if hits:
            violations[_rel(path)] = sorted(set(hits))
    assert not violations, (
        "Coordinates must come from Settings.demo_stop_coords, not numeric "
        f"literals: {violations}"
    )


# ===========================================================================
# R7.6 -- no MBTA / Bluebikes logo or brand assets referenced.
# ===========================================================================
_LOGO_RE = re.compile(
    r"(mbta|bluebikes|massdot)[\w/\-]*\.(png|svg|jpg|jpeg|gif|webp)",
    re.IGNORECASE,
)
_ASSET_RE = re.compile(r"(logo|brandmark|wordmark)[\w/\-]*\.(png|svg|jpg|jpeg|gif|webp)",
                       re.IGNORECASE)


def test_no_logo_assets_referenced():
    # Feature: unghosted-demo, R7.6 -- no MBTA/Bluebikes logos or brand marks.
    violations: dict[str, list[str]] = {}
    for path in _scanned_files():
        hits = []
        for literal in _string_constants(_parse(path)):
            if _LOGO_RE.search(literal) or _ASSET_RE.search(literal):
                hits.append(literal)
        if hits:
            violations[_rel(path)] = sorted(set(hits))
    assert not violations, (
        "No MBTA/Bluebikes logo or brand asset may be referenced: "
        f"{violations}"
    )


# ===========================================================================
# R11.7 -- .env is never tracked by git (.env.example is fine).
# ===========================================================================
def test_env_file_is_not_tracked():
    # Feature: unghosted-demo, R11.7 -- secrets stay in .env, which is untracked.
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:  # pragma: no cover
        pytest.skip(f"git ls-files unavailable: {exc}")

    tracked = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    # Any tracked path whose final component is exactly ".env" is a violation;
    # ".env.example" and similar are allowed.
    offenders = [p for p in tracked if Path(p).name == ".env"]
    assert not offenders, f".env must not be tracked by git: {offenders}"
