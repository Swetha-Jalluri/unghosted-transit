---
inclusion: always
---
# Project structure
core/          engine (owner A): feeds, collector, static_load, labeler, arrivals,
               bus_trust, dock_trust, backup, model, findings, replay,
               contracts.py and service.py (the contract)
tests/core/    A's tests; tests/fixtures/ (raw feed samples + mock/ outputs)
data/          raw.db (ignored), sample.db (committed, < 25 MB)
artifacts/     findings.json, rates.json, model.joblib
streamlit_app.py  app entry at the repo root (owner B); pages in app/
api/           FastAPI /v1 (owner B); tests/api/
mcp_server/    FastMCP server, read-only tools (owner B); tests/mcp/
docs/          DATA.md, FINDINGS.md (A); WRITEUP.md (B); kiro-journal-A.md, kiro-journal-B.md; screenshots/A, screenshots/B
.kiro/         steering (A), specs/unghosted-core (A), specs/unghosted-demo (B), hooks (B), settings/mcp.json (B)
