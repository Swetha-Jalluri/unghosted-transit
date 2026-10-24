"""Settings tests: legal-text pins and the config override property.

Two things are guarded here:

1. Pin tests that keep the shared legal strings from drifting. ``app.settings``
   is the single source of the Disclaimer and Attribution shown by the app, API
   and MCP server, and ``ATTRIBUTION`` must equal ``core.service.ATTRIBUTION``
   joined with a single space (the Glossary join invariant), while
   ``DISCLAIMER`` must match the Glossary string word for word.

2. Property 16 (R11.6): for any mapping of override values, ``load_settings``
   uses the override for each key that exists in the defaults, ignores unknown
   keys and wrong types, and never writes to the config file.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import yaml
from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

import core.service as core_service
from app.settings import (
    ATTRIBUTION,
    DISCLAIMER,
    SETTINGS,
    Settings,
    load_settings,
)


# ---------------------------------------------------------------------------
# Pin tests: the legal strings are a single source and must not drift.
# ---------------------------------------------------------------------------
def test_attribution_is_core_service_list_joined_by_space():
    """ATTRIBUTION equals the core.service attribution list joined by a space."""
    assert ATTRIBUTION == " ".join(core_service.ATTRIBUTION)


def test_disclaimer_matches_core_service_disclaimer():
    """DISCLAIMER matches the Glossary string word for word."""
    assert DISCLAIMER == core_service.DISCLAIMER


def test_settings_singleton_is_a_settings_instance():
    """The module singleton is a Settings and exposes the legal strings elsewhere."""
    assert isinstance(SETTINGS, Settings)


# ---------------------------------------------------------------------------
# Strategies for Property 16.
#
# A frozen Settings() gives the defaults we override against. For each top-level
# field we generate values of three flavours so the property exercises every
# branch of load_settings:
#   * a type-correct override (should win),
#   * a wrong-typed override (should be ignored, default kept),
#   * unknown keys that are not Settings fields (should be ignored entirely).
# The expected result is derived from the very same rules load_settings uses, so
# the test asserts behaviour rather than re-encoding a fixed answer.
# ---------------------------------------------------------------------------
_DEFAULTS = Settings()

# Scalar field names by default type, used to build type-correct/wrong values.
_INT_FIELDS = ["replay_play_speed", "dock_limit"]
_STR_FIELDS = ["mbta_api_base_url", "api_base_url", "display_tz"]
_LIST_STR_FIELDS = ["cors_origins"]
_TUPLE_FIELDS = ["mcp_tools", "modes"]
_NESTED_INT_FIELDS = ["limit"]  # {"default","min","max"} ints
_NESTED_NUM_FIELDS = ["walk_min"]  # {"default","min","max"} numbers
_DICT_ROUTE_FIELDS = ["api_routes"]  # str -> str

# Wrong-typed values: a type that _type_matches / _coerce_value rejects for each
# default so the default must be kept.
_WRONG_FOR = {
    "replay_play_speed": "not-an-int",
    "dock_limit": True,  # bool rejected where int expected
    "mbta_api_base_url": 123,
    "api_base_url": ["not", "a", "string"],
    "display_tz": 3.14,
    "cors_origins": "not-a-list",
    "mcp_tools": "not-a-list-or-tuple",
    "modes": 42,
    "limit": "not-a-dict",
    "walk_min": 7,
    "api_routes": ["not", "a", "dict"],
}

_SETTINGS_FIELD_NAMES = set(_DEFAULTS.__dataclass_fields__)


@st.composite
def override_mappings(draw):
    """Build (override_mapping, expected_settings_kwargs).

    ``override_mapping`` is what we write to the temp YAML file. The second item
    records, per field we touched, the value we expect to see on the returned
    Settings (either the applied override or the preserved default).
    """
    mapping: dict = {}
    expected: dict = {}

    # ---- type-correct scalar overrides -----------------------------------
    for name in _INT_FIELDS:
        if draw(st.booleans()):
            value = draw(st.integers(min_value=0, max_value=1000))
            mapping[name] = value
            expected[name] = value

    for name in _STR_FIELDS:
        if draw(st.booleans()):
            value = draw(st.text(min_size=0, max_size=20))
            mapping[name] = value
            expected[name] = value

    # cors_origins: a list[str] default. _type_matches accepts any list.
    for name in _LIST_STR_FIELDS:
        if draw(st.booleans()):
            value = draw(st.lists(st.text(max_size=12), max_size=4))
            mapping[name] = value
            expected[name] = value

    # tuple defaults (mcp_tools, modes): YAML has no tuple, a list override is
    # coerced to a tuple; anything else keeps the default.
    for name in _TUPLE_FIELDS:
        if draw(st.booleans()):
            value = draw(st.lists(st.text(max_size=12), max_size=4))
            mapping[name] = value
            expected[name] = tuple(value)

    # nested int dicts (limit): only keys present in the default and int-typed
    # are merged.
    for name in _NESTED_INT_FIELDS:
        if draw(st.booleans()):
            default_dict = getattr(_DEFAULTS, name)
            override_dict = {}
            merged = dict(default_dict)
            for key in default_dict:
                if draw(st.booleans()):
                    v = draw(st.integers(min_value=0, max_value=100))
                    override_dict[key] = v
                    merged[key] = v
            # Add a key not present in the default; must be ignored by the merge.
            if draw(st.booleans()):
                override_dict["bogus_key"] = draw(st.integers())
            mapping[name] = override_dict
            expected[name] = merged

    # nested number dicts (walk_min): the override only wins when its type
    # matches the per-key default type. The default values are ints, so a float
    # override is rejected for them (bool is also rejected for a number); an int
    # override wins. A float only wins where the default value is itself a float.
    for name in _NESTED_NUM_FIELDS:
        if draw(st.booleans()):
            default_dict = getattr(_DEFAULTS, name)
            override_dict = {}
            merged = dict(default_dict)
            for key, default_value in default_dict.items():
                if not draw(st.booleans()):
                    continue
                if isinstance(default_value, bool):
                    v = draw(st.booleans())
                elif isinstance(default_value, int):
                    v = draw(st.integers(min_value=0, max_value=60))
                else:  # float default: accept int or float
                    v = draw(
                        st.one_of(
                            st.integers(min_value=0, max_value=60),
                            st.floats(
                                min_value=0,
                                max_value=60,
                                allow_nan=False,
                                allow_infinity=False,
                            ),
                        )
                    )
                override_dict[key] = v
                merged[key] = v
            # Optionally feed a wrong-typed value (float to an int-default key)
            # for a key we did not already override: it must be rejected and the
            # default kept, exercising the per-key type guard inside the merge.
            int_keys = [
                k for k, dv in default_dict.items()
                if isinstance(dv, int) and not isinstance(dv, bool)
                and k not in override_dict
            ]
            if int_keys and draw(st.booleans()):
                bad_key = int_keys[0]
                override_dict[bad_key] = draw(
                    st.floats(
                        min_value=0.5,
                        max_value=59.5,
                        allow_nan=False,
                        allow_infinity=False,
                    ).filter(lambda x: x != int(x))
                )
                # merged keeps the default for bad_key (no change).
            mapping[name] = override_dict
            expected[name] = merged

    # str->str dict (api_routes): keys present in default with str values win.
    for name in _DICT_ROUTE_FIELDS:
        if draw(st.booleans()):
            default_dict = getattr(_DEFAULTS, name)
            override_dict = {}
            merged = dict(default_dict)
            for key in default_dict:
                if draw(st.booleans()):
                    v = draw(st.text(min_size=1, max_size=20))
                    override_dict[key] = v
                    merged[key] = v
            mapping[name] = override_dict
            expected[name] = merged

    # ---- wrong-typed overrides: present in the file but default must stay ---
    wrong_candidates = draw(
        st.lists(st.sampled_from(sorted(_WRONG_FOR)), unique=True, max_size=4)
    )
    for name in wrong_candidates:
        if name in mapping:
            continue  # already has a valid override this round
        mapping[name] = _WRONG_FOR[name]
        expected[name] = getattr(_DEFAULTS, name)  # default preserved

    # ---- unknown keys: never a Settings field, must be ignored -------------
    unknown = draw(
        st.dictionaries(
            keys=st.text(min_size=1, max_size=10).filter(
                lambda k: k not in _SETTINGS_FIELD_NAMES
            ),
            values=st.one_of(st.integers(), st.text(max_size=8), st.booleans()),
            max_size=4,
        )
    )
    mapping.update(unknown)

    return mapping, expected


@hyp_settings(max_examples=150)
@given(data=override_mappings())
def test_property_16_overrides_applied_without_writing(data):
    # Feature: unghosted-demo, Property 16: config.yaml overrides defaults without being written
    # Validates: Requirements 11.6
    mapping, expected = data

    # A fresh temp dir per generated example (tmp_path is function-scoped and
    # not reset between Hypothesis inputs, so we manage the directory here).
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "config.yaml"
        config_file.write_text(yaml.safe_dump(mapping), encoding="utf-8")
        before = config_file.read_bytes()

        result = load_settings(config_file)

        # Each key we expect is reflected: valid overrides applied, wrong types
        # kept at their default, nested dicts merged key by key.
        for field_name, want in expected.items():
            assert getattr(result, field_name) == want, field_name

        # Unknown keys never add attributes to the frozen Settings instance.
        unknown_keys = set(mapping) - _SETTINGS_FIELD_NAMES
        for key in unknown_keys:
            assert not hasattr(result, key)

        # Fields we never touched keep their defaults.
        untouched = _SETTINGS_FIELD_NAMES - set(expected)
        for field_name in untouched:
            if field_name in mapping:
                continue  # was a wrong-typed override already asserted above
            assert getattr(result, field_name) == getattr(
                _DEFAULTS, field_name
            ), field_name

        # The config file is never written: its bytes are unchanged.
        after = config_file.read_bytes()
        assert after == before

        # The returned value is still a usable, frozen Settings.
        assert isinstance(result, Settings)


def test_property_16_missing_config_keeps_defaults():
    # Feature: unghosted-demo, Property 16: config.yaml overrides defaults without being written
    # Validates: Requirements 11.6
    # A path that does not exist yields the untouched defaults and writes nothing.
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "does_not_exist.yaml"
        result = load_settings(missing)
        assert result == Settings()
        assert not missing.exists()
