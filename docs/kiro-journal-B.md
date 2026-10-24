# Kiro journal (B)

Agent hooks: created 3 hooks via Ask Kiro — tests on save (api/mcp), README API/MCP sync on save, manual pre-push safety check (.kiro not ignored, no .env/raw.db, no files >50MB, no secrets). Kiro tested the pre-push hook against a clean repo and a deliberately failing repo.
