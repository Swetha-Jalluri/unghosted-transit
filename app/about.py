"""About page.

What Unghosted is, who it is for, and the principles it holds to. Static
content only.
"""
from __future__ import annotations

import streamlit as st

from app.components import footer, page_header
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

    st.subheader("Modes")
    st.markdown(
        """
- **Live** — current feeds
- **Demo** — sample data or mocks
- **Replay** — a time slider over logged data, with hindsight outcomes
        """
    )

    footer()
