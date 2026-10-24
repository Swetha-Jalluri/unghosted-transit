"""About page.

What Unghosted is, who it is for, and the principles it holds to. Static
content only: guardrails, evals, observability, honest limits, roadmap, and
the status vocabulary. No logos, no brand marks, no unlabeled numbers. The
footer (attribution + disclaimer) is rendered by main(), not here.
"""
from __future__ import annotations

import streamlit as st

from app.components import page_header
from app.theme import APP_TAGLINE


def render() -> None:
    page_header("About")

    st.markdown(f"**{APP_TAGLINE}**")
    st.write(
        "Unghosted is a trust layer for transit apps. For any MBTA bus "
        "prediction or Bluebikes dock, it answers three questions:"
    )
    st.markdown(
        """
1. **Will it really be there?** — a status and a chance, with the sample size behind it.
2. **When, realistically?** — a time range, not a single number.
3. **If not, what is the backup?** — a nearby alternative when the first option looks shaky.
        """
    )

    st.subheader("Who it's for")
    st.markdown(
        """
- Transit app teams, through the REST API
- AI assistants, through the MCP server
- Riders, through the apps that embed us
- Bikeshare operations and city / MBTA analysts
        """
    )

    st.subheader("Principles")
    st.markdown(
        """
- **Never claim certainty.** Every output shows data age, attribution and sample sizes.
- We say *"disappeared before arrival"*, never *"proven ghost"*.
- Placeholder numbers are never presented as measured results.
- Status is always shown as a **word**, never by color alone.
- No logos or brand marks. No analytics, no tracking, no location requests — we use a stop picker.
        """
    )

    st.subheader("Statuses")
    st.write(
        "Every trust answer carries one of four statuses. The status is always "
        "shown as its word, never by color alone."
    )
    st.markdown(
        """
- **confirmed** — a vehicle or dock reading backs the answer and it looks dependable right now.
- **estimate** — the answer is schedule- or model-based, so treat it as a best guess rather than a certainty.
- **unreliable** — the signal is weak, stale or contradictory, so the answer should not be trusted.
- **hidden** — the item fails our quality checks (for example non-revenue trips or invalid readings) and is **never shown to users**; it is only counted.
        """
    )

    st.subheader("Guardrails")
    st.write(
        "The decision rules that turn raw feeds into a status, a chance and an "
        "ETA range are pure, deterministic functions with no network, file, "
        "clock or randomness in them. They are covered by property-based tests "
        "that check status words, chance formatting, hindsight labels and "
        "data-age formatting across wide ranges of inputs, so the trust rules "
        "cannot silently drift. User-facing text never claims certainty and "
        "never uses the words \"ghost\" or \"proven\"."
    )

    st.subheader("Evals")
    st.write(
        "We measure rather than assert. Vanish rates are broken down by status, "
        "by uncertainty code and by route; model quality is reported with AUC, "
        "Brier score and a calibration table; ETA accuracy compares range hits "
        "against single-point hits. Every figure carries its sample size, and "
        "while the findings are a placeholder they are labelled as such and "
        "never presented as a measured result."
    )

    st.subheader("Observability")
    st.write(
        "The Operator view exposes a health panel sourced from the Service: "
        "last poll time, polls in the last hour, poll success rate, row counts, "
        "data age per feed, which modes are enabled, and the model method. "
        "Missing values are shown as \"not available\" rather than guessed, so "
        "the panel stays honest about what the collector actually knows."
    )

    st.subheader("Honest limits")
    st.write(
        "We do not work around the Service gaps below; we state them plainly so "
        "you can tell what this demo does and does not do."
    )
    st.markdown(
        """
- `get_nearby_docks` has no `at_ts` parameter, so the docks shown in Replay mode do not change as you move the time slider.
- `get_dock_trust` ignores `walk_min` and `mode`, so those inputs have no effect on a dock's backups.
- Demo mode never raises `LiveDataUnavailable`, so the Live fallback described for the Rider view is verified with stubs rather than a real outage.
- `Health.data_age_sec` may omit keys, which the Operator view shows as "not available".
        """
    )
    st.write(
        "The REST API and the MCP server are unauthenticated and read-only by "
        "design: they serve public demo data and expose no tool that writes or "
        "changes anything."
    )

    st.subheader("Roadmap")
    st.markdown(
        """
- Deploy the API and MCP server on **AWS** (managed containers plus a managed datastore) so the trust layer can run continuously beyond the demo.
- Widen coverage from the demo stops to full MBTA bus and Bluebikes networks, backfilling the logged history that evals depend on.
- Replace the placeholder findings with a trained, calibrated model re-fit on a rolling window of real labels.
- Add alerting on the health panel so operators are notified when data collection stalls.
        """
    )
