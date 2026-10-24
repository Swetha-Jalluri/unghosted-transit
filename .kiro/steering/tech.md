---
inclusion: always
---
# Tech stack
- Python 3.11, managed with **uv only**: `uv add` (A only), `uv sync`, `uv run ...`. Never pip, never requirements.txt.
- Dependencies live in pyproject.toml + uv.lock (both committed; Streamlit Cloud installs from uv.lock).
- Libraries: requests, pandas, numpy, scikit-learn, joblib, pyyaml, python-dotenv, fastapi, uvicorn, pydantic, httpx, streamlit, altair, fastmcp. Dev: pytest, hypothesis.
- Storage: SQLite (sqlite3). Times stored as POSIX seconds UTC; display in America/New_York.
- Config in config.yaml; secrets only in .env (never committed, never pasted into chat, steering or hooks).
- Decision logic (status, reasons, chances, replay outcomes) must be pure deterministic functions with property-based tests (Hypothesis). These tests are our guardrails.
- Run commands from the repo root: `uv run pytest -q`, `uv run streamlit run streamlit_app.py`, `uv run uvicorn api.main:app --reload`, `uv run python -m mcp_server.server`.
- Keep spec documents concise: short acceptance criteria, no long test plans or diagrams.

## No hardcoding
- All URLs, routes, stop IDs, station IDs, thresholds and intervals come from config.yaml (or .env for secrets). Never hardcode them in code.
- Mock data lives only in tests/fixtures/ and is used only as a fallback when real data is missing; never inside core logic.
- No made-up numbers in code, docs or UI; findings come from logged data.
- Test fixtures must be real snapshots from the live feeds (trimmed).
