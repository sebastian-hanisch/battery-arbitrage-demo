import datetime

import battery_permalink as permalink


def test_parse_float_valid_within_range():
    assert permalink.parse_float({"x": "12.5"}, "x", 0.0, 50.0, -1.0) == 12.5


def test_parse_float_missing_key_falls_back_to_default():
    assert permalink.parse_float({}, "x", 0.0, 50.0, 7.0) == 7.0


def test_parse_float_non_numeric_falls_back_to_default():
    assert permalink.parse_float({"x": "not-a-number"}, "x", 0.0, 50.0, 7.0) == 7.0


def test_parse_float_out_of_range_falls_back_to_default():
    assert permalink.parse_float({"x": "999"}, "x", 0.0, 50.0, 7.0) == 7.0


def test_parse_float_zero_default_is_not_treated_as_falsy():
    # A legitimate default/parsed value of 0.0 must survive - guards against
    # an `or default` style implementation that would misfire on 0.0.
    assert permalink.parse_float({"x": "0"}, "x", 0.0, 1.0, 0.5) == 0.0
    assert permalink.parse_float({}, "x", 0.0, 1.0, 0.0) == 0.0


def test_parse_choice_valid_value():
    assert permalink.parse_choice({"m": "live"}, "m", {"live", "beispiel"}, "beispiel") == "live"


def test_parse_choice_invalid_or_missing_falls_back():
    assert permalink.parse_choice({"m": "garbage"}, "m", {"live", "beispiel"}, "beispiel") == "beispiel"
    assert permalink.parse_choice({}, "m", {"live", "beispiel"}, "beispiel") == "beispiel"


def test_parse_date_valid_iso_string():
    assert permalink.parse_date({"d": "2026-06-15"}, "d") == datetime.date(2026, 6, 15)


def test_parse_date_missing_or_malformed_returns_none():
    assert permalink.parse_date({}, "d") is None
    assert permalink.parse_date({"d": "not-a-date"}, "d") is None


def test_build_params_preset_mode_includes_tag_not_date():
    params = permalink.build_params(
        mode=permalink.MODE_PRESET, preset_name="Volatiler Tag (13.08.2026)",
        selected_date=datetime.date(2026, 6, 15),  # stale leftover, must not leak into the URL
        capacity_kwh=10.0, max_rate_kw=5.0, efficiency=0.9, start_fraction=0.5,
    )
    assert params[permalink.PARAM_MODE] == permalink.MODE_PRESET
    assert params[permalink.PARAM_PRESET] == "Volatiler Tag (13.08.2026)"
    assert permalink.PARAM_DATE not in params


def test_build_params_live_mode_includes_date_not_tag():
    params = permalink.build_params(
        mode=permalink.MODE_LIVE, preset_name="stale preset",  # must not leak into the URL
        selected_date=datetime.date(2026, 6, 15),
        capacity_kwh=10.0, max_rate_kw=5.0, efficiency=0.9, start_fraction=0.5,
    )
    assert params[permalink.PARAM_MODE] == permalink.MODE_LIVE
    assert params[permalink.PARAM_DATE] == "2026-06-15"
    assert permalink.PARAM_PRESET not in params


def test_build_params_numbers_are_compact():
    params = permalink.build_params(
        mode=permalink.MODE_PRESET, preset_name="x", selected_date=None,
        capacity_kwh=10.0, max_rate_kw=5.0, efficiency=0.9, start_fraction=0.5,
    )
    assert params[permalink.PARAM_CAPACITY] == "10"
    assert params[permalink.PARAM_EFFICIENCY] == "0.9"


def test_round_trip_preset_mode():
    built = permalink.build_params(
        mode=permalink.MODE_PRESET, preset_name="Ruhiger Tag (17.08.2026)", selected_date=None,
        capacity_kwh=12.5, max_rate_kw=7.5, efficiency=0.85, start_fraction=0.25,
    )
    assert permalink.parse_choice(built, permalink.PARAM_MODE, {permalink.MODE_PRESET, permalink.MODE_LIVE}, "?") == permalink.MODE_PRESET
    assert permalink.parse_choice(built, permalink.PARAM_PRESET, {"Ruhiger Tag (17.08.2026)"}, "?") == "Ruhiger Tag (17.08.2026)"
    assert permalink.parse_float(built, permalink.PARAM_CAPACITY, 1.0, 50.0, -1.0) == 12.5
    assert permalink.parse_float(built, permalink.PARAM_MAX_RATE, 0.5, 25.0, -1.0) == 7.5
    assert permalink.parse_float(built, permalink.PARAM_EFFICIENCY, 0.5, 1.0, -1.0) == 0.85
    assert permalink.parse_float(built, permalink.PARAM_START_FRACTION, 0.0, 1.0, -1.0) == 0.25


def test_round_trip_live_mode():
    built = permalink.build_params(
        mode=permalink.MODE_LIVE, preset_name=None, selected_date=datetime.date(2026, 1, 15),
        capacity_kwh=20.0, max_rate_kw=10.0, efficiency=0.92, start_fraction=0.0,
    )
    assert permalink.parse_date(built, permalink.PARAM_DATE) == datetime.date(2026, 1, 15)
    assert permalink.parse_float(built, permalink.PARAM_START_FRACTION, 0.0, 1.0, -1.0) == 0.0
