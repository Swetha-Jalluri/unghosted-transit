---
inclusion: always
---
# Collaboration rules (two people, one repo)
- A = Swetha (branch a-core). B = teammate (branch b-app). Nobody commits to main; main changes only by merging PRs.
- Sync: author merges a PR into main; the other runs `git pull origin main` on their branch, then `uv sync`.
- **Ownership. Before editing any file, check this list. If it belongs to the other teammate, STOP and tell the user.**
  - A owns: core/, tests/core/, tests/fixtures/, data/, artifacts/, pyproject.toml, uv.lock, .python-version, config.yaml, .gitignore, .env.example, .kiro/steering/, .kiro/specs/unghosted-core/, docs/DATA.md, docs/FINDINGS.md, docs/kiro-journal-A.md, docs/screenshots/A/.
  - B owns: streamlit_app.py, app/, .streamlit/, api/, tests/api/, mcp_server/, tests/mcp/, .kiro/specs/unghosted-demo/, .kiro/hooks/, .kiro/settings/mcp.json, README.md, LICENSE, docs/WRITEUP.md, docs/kiro-journal-B.md, docs/screenshots/B/.
- B's code imports only core.service and core.contracts. A never renames or removes contract names; only optional additions, announced.
- Only A changes dependencies (`uv add`). B asks A.
- Commit small, prefixed [A] or [B]. Run tests before every push.
- Never commit .env, data/raw.db, .venv/. Never add .kiro to .gitignore.
- On a merge conflict: stop, tell the user, resolve keeping both changes.
