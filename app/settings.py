"""Shared settings for the Unghosted delivery layer (app, API, MCP).

Single source of defaults, legal strings and bounds. Imports no Streamlit, so
``api/`` and ``mcp_server/`` can use it without pulling in the UI. A value under
the same top-level key in ``config.yaml`` overrides the matching default here;
``config.yaml`` is read-only and never written (R11.5, R11.6).

The ``demo_stop_coords`` block between the DEMO_STOP_COORDS markers is filled
once by ``scripts/fetch_demo_coords.py``; it stays empty until that script runs
and no coordinate is ever guessed (R11.9, R11.10).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Legal text (word for word from the Glossary; single source for app/API/MCP).
# ATTRIBUTION is the core.service attribution list joined with a single space.
# ---------------------------------------------------------------------------
DISCLAIMER = (
    "Unofficial. Not affiliated with or endorsed by MBTA, MassDOT or Bluebikes. "
    "For information only."
)

ATTRIBUTION = (
    "Data: MBTA GTFS-realtime (MassDOT Developers License Agreement); "
    "Bluebikes GBFS (Bluebikes Data License Agreement)."
)

# ---------------------------------------------------------------------------
# Repo root and config path. config.yaml lives at the repo root (A-owned).
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yaml"

# ---------------------------------------------------------------------------
# Demo stop coordinates. Filled once by scripts/fetch_demo_coords.py, which
# rewrites ONLY the text between the two markers below. Empty by default.
# Keys are stop ids; values are {"lat": float, "lon": float}.
# ---------------------------------------------------------------------------
# BEGIN DEMO_STOP_COORDS
_DEMO_STOP_COORDS: dict[str, dict[str, float]] = {}
# END DEMO_STOP_COORDS


@dataclass(frozen=True)
class Settings:
    """Immutable settings shared by the app, API and MCP server."""

    # Demo stop coordinates keyed by stop id (filled by the one-time script).
    demo_stop_coords: dict[str, dict[str, float]] = field(
        default_factory=lambda: dict(_DEMO_STOP_COORDS)
    )

    # MBTA V3 API base URL, used only by scripts/fetch_demo_coords.py.
    mbta_api_base_url: str = "https://api-v3.mbta.com"

    # Base URL of the REST API, shown on the API & MCP page.
    api_base_url: str = "http://localhost:8000"

    # REST route paths under /v1 (API and API & MCP page).
    api_routes: dict[str, str] = field(
        default_factory=lambda: {
            "bus_trust": "/v1/bus-trust",
            "dock_trust": "/v1/dock-trust",
            "nearby_docks": "/v1/nearby-docks",
            "findings": "/v1/findings",
            "health": "/v1/health",
            "replay_window": "/v1/replay-window",
        }
    )

    # The five MCP tool names (MCP server and API & MCP page).
    mcp_tools: tuple[str, ...] = (
        "list_demo_stops",
        "check_bus_trust",
        "check_dock_trust",
        "nearby_docks",
        "todays_findings",
    )

    # CORS allow-list. Empty means no CORS headers are returned.
    cors_origins: list[str] = field(default_factory=list)

    # Replay: logged seconds elapsed per real second.
    replay_play_speed: int = 60

    # Walk-minutes default/min/max (default matches the service default of 5).
    walk_min: dict[str, float] = field(
        default_factory=lambda: {"default": 5, "min": 1, "max": 30}
    )

    # Number of nearby docks requested (matches the service default).
    dock_limit: int = 3

    # Bus/dock prediction limit default/min/max (default matches the service).
    limit: dict[str, int] = field(
        default_factory=lambda: {"default": 5, "min": 1, "max": 20}
    )

    # Display time zone for all user-facing times.
    display_tz: str = "America/New_York"

    # The three modes understood by the service.
    modes: tuple[str, ...] = ("live", "demo", "replay")


def _merge_mapping(default: dict[str, Any], override: Any) -> dict[str, Any]:
    """Merge a nested mapping override key by key.

    Only keys already present in ``default`` are considered, and only when the
    override value's type matches the default value's type. Unknown keys and
    wrong types are ignored.
    """
    if not isinstance(override, dict):
        return default
    merged = dict(default)
    for key, default_value in default.items():
        if key not in override:
            continue
        candidate = override[key]
        if _type_matches(default_value, candidate):
            merged[key] = candidate
    return merged


def _type_matches(default_value: Any, candidate: Any) -> bool:
    """Return True when ``candidate`` is an acceptable type for the default.

    Booleans are rejected where a number is expected (``bool`` is a subclass of
    ``int``). Ints are acceptable where a float default is used.
    """
    if isinstance(default_value, bool):
        return isinstance(candidate, bool)
    if isinstance(default_value, int):
        return isinstance(candidate, int) and not isinstance(candidate, bool)
    if isinstance(default_value, float):
        return (
            isinstance(candidate, (int, float)) and not isinstance(candidate, bool)
        )
    return isinstance(candidate, type(default_value))


def _coerce_value(default_value: Any, candidate: Any) -> Any:
    """Return the override to apply for a top-level Settings key, or the default.

    Nested dicts are merged key by key; other values replace the default only
    when their type matches. Wrong types are ignored (default is kept).
    """
    if isinstance(default_value, dict):
        return _merge_mapping(default_value, candidate)
    if isinstance(default_value, tuple):
        # Allow a list override for a tuple default (e.g. modes), as YAML has
        # no tuple type; keep it a tuple to stay frozen/hashable.
        if isinstance(candidate, list):
            return tuple(candidate)
        return default_value
    if _type_matches(default_value, candidate):
        return candidate
    return default_value


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Build :class:`Settings`, overriding defaults from ``config.yaml``.

    ``config.yaml`` is read with ``yaml.safe_load`` and never written. For each
    field of :class:`Settings` whose name also appears at the top level of the
    config, the config value overrides the default (nested dicts merged key by
    key, tuple defaults accept a list). Unknown keys and wrong types are
    ignored. A missing or unreadable config leaves every default in place.
    """
    base = Settings()
    path = Path(config_path) if config_path is not None else CONFIG_PATH

    try:
        with open(path, "r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return base

    if not isinstance(loaded, dict):
        return base

    overrides: dict[str, Any] = {}
    for field_name in base.__dataclass_fields__:
        if field_name not in loaded:
            continue
        default_value = getattr(base, field_name)
        overrides[field_name] = _coerce_value(default_value, loaded[field_name])

    if not overrides:
        return base
    return replace(base, **overrides)


# Module-level singleton used across the delivery layer.
SETTINGS = load_settings()
