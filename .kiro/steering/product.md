---
inclusion: always
---
# Product: Unghosted
"Unghosted: a trust layer for transit apps. Apps tell you when. We tell you whether."

For any MBTA bus prediction or Bluebikes dock, Unghosted answers:
1. Will it really be there? (status + chance with sample size)
2. When, realistically? (a time range, not one number)
3. If not, what is the backup?

Users: transit app teams (REST API), AI assistants (MCP server), riders (through those apps), bikeshare operations, city/MBTA analysts. Demo audience: hackathon judges (Hackachusetts 2026, Civic Action track).

Statuses: confirmed (green), estimate (amber), unreliable (red), hidden (never shown). Always show the word, never color alone.

Principles (non-negotiable):
- Never claim certainty. Every output shows data age, attribution and sample sizes.
- Say "disappeared before arrival", never "proven ghost".
- Never present placeholder numbers as measured results (use is_placeholder).
- Every user-facing output includes the disclaimer: "Unofficial. Not affiliated with or endorsed by MBTA, MassDOT or Bluebikes. For information only."
- Attribution: "Data: MBTA GTFS-realtime (MassDOT Developers License Agreement); Bluebikes GBFS (Bluebikes Data License Agreement)."
- No MBTA/Bluebikes logos or brand marks. No user tracking, analytics or location requests (use a stop picker).
- Modes: live (current feeds), demo (sample.db or mocks), replay (time slider over logged data with hindsight outcomes).
