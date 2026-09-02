"""Reading and writing the demo's shareable state via URL query parameters
("permalinks"): scenario, battery settings and (in live mode) the chosen
date all round-trip through the URL, so a copied link reproduces exactly
what the sender was looking at.

Parsing is deliberately forgiving: a missing, malformed, or out-of-range
parameter just falls back to the given default instead of raising, since
this also has to survive hand-edited or stale URLs - never a reason for
the demo to crash.
"""

import datetime

MODE_PRESET = "beispiel"
MODE_LIVE = "live"

PARAM_MODE = "modus"
PARAM_PRESET = "tag"
PARAM_DATE = "datum"
PARAM_CAPACITY = "kapazitaet"
PARAM_MAX_RATE = "leistung"
PARAM_EFFICIENCY = "wirkungsgrad"
PARAM_START_FRACTION = "start"


def parse_float(params: dict, key: str, lo: float, hi: float, default: float) -> float:
    try:
        value = float(params[key])
    except (KeyError, ValueError, TypeError):
        return default
    return value if lo <= value <= hi else default


def parse_choice(params: dict, key: str, allowed, default: str) -> str:
    value = params.get(key)
    return value if value in allowed else default


def parse_date(params: dict, key: str) -> datetime.date | None:
    value = params.get(key)
    if value is None:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def format_number(value: float) -> str:
    """Compact string for a URL query value - no unnecessary trailing zeros."""
    return f"{value:g}"


def build_params(
    *,
    mode: str,
    preset_name: str | None,
    selected_date: datetime.date | None,
    capacity_kwh: float,
    max_rate_kw: float,
    efficiency: float,
    start_fraction: float,
) -> dict:
    """The full set of query parameters representing the current state.
    Only the source-specific one of `tag`/`datum` is included, matching
    whichever mode is active, so switching modes doesn't leave a stale
    parameter from the other one behind in the URL."""
    params = {
        PARAM_MODE: mode,
        PARAM_CAPACITY: format_number(capacity_kwh),
        PARAM_MAX_RATE: format_number(max_rate_kw),
        PARAM_EFFICIENCY: format_number(efficiency),
        PARAM_START_FRACTION: format_number(start_fraction),
    }
    if mode == MODE_PRESET and preset_name is not None:
        params[PARAM_PRESET] = preset_name
    elif mode == MODE_LIVE and selected_date is not None:
        params[PARAM_DATE] = selected_date.isoformat()
    return params
