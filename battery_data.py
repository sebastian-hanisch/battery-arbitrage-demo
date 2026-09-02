"""Live day-ahead prices from SMARD.de (Bundesnetzagentur's market
transparency platform), as an alternative to the fixed presets in
battery_constants.py.

SMARD publishes quarter-hourly data in weekly chunks under a stable,
undocumented but long-stable JSON API:

  - index_quarterhour.json lists the start timestamp (UTC ms) of every
    available weekly chunk for a given filter/region.
  - {filter}_{region}_quarterhour_{chunk_ts}.json holds that week's
    [timestamp_ms, price_or_null] pairs, filter 4169 = "Großhandelspreise
    Deutschland/Luxemburg" (EUR/MWh), region "DE-LU".

A calendar day is defined in German local time (Europe/Berlin), matching
how the day-ahead auction itself is structured - not UTC midnight. Because
chunk boundaries don't always line up neatly with a requested day (mainly
around DST changes), we fetch every chunk that overlaps the day's local
time range rather than assuming a single chunk holds it.
"""

import datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st

SMARD_FILTER = 4169
SMARD_REGION = "DE-LU"
SMARD_BASE = f"https://www.smard.de/app/chart_data/{SMARD_FILTER}/{SMARD_REGION}"
SMARD_INDEX_URL = f"{SMARD_BASE}/index_quarterhour.json"
SMARD_CHUNK_URL = SMARD_BASE + "/" + str(SMARD_FILTER) + "_" + SMARD_REGION + "_quarterhour_{chunk_ts}.json"
CHUNK_SPAN_MS = 7 * 24 * 3600 * 1000

BERLIN = ZoneInfo("Europe/Berlin")
REQUEST_TIMEOUT_S = 10


class SmardUnavailableError(RuntimeError):
    """Raised when a day's prices can't be fetched or aren't fully published yet."""


def _local_day_bounds_ms(day: datetime.date) -> tuple[int, int]:
    start = datetime.datetime.combine(day, datetime.time.min, tzinfo=BERLIN)
    end = start + datetime.timedelta(days=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_index() -> list[int]:
    resp = requests.get(SMARD_INDEX_URL, timeout=REQUEST_TIMEOUT_S)
    resp.raise_for_status()
    return resp.json()["timestamps"]


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_chunk(chunk_ts: int) -> list[list]:
    url = SMARD_CHUNK_URL.format(chunk_ts=chunk_ts)
    resp = requests.get(url, timeout=REQUEST_TIMEOUT_S)
    resp.raise_for_status()
    return resp.json()["series"]


def available_date_range() -> tuple[datetime.date, datetime.date]:
    """Earliest date with published data, and the latest date that should
    be fully published (yesterday - today's/tomorrow's auction results
    aren't necessarily complete yet at any given moment)."""
    timestamps = _fetch_index()
    earliest = datetime.datetime.fromtimestamp(timestamps[0] / 1000, tz=BERLIN).date()
    yesterday = datetime.datetime.now(tz=BERLIN).date() - datetime.timedelta(days=1)
    return earliest, yesterday


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_day_prices(day: datetime.date) -> list[float]:
    """Returns 24 hourly EUR/MWh prices for `day` (German local calendar
    day), averaged from SMARD's quarter-hourly data. Raises
    SmardUnavailableError if the day isn't available or isn't fully
    published (e.g. a future date, or missing/null values)."""
    day_start_ms, day_end_ms = _local_day_bounds_ms(day)

    try:
        timestamps = _fetch_index()
    except requests.RequestException as exc:
        raise SmardUnavailableError(f"SMARD-Index nicht erreichbar: {exc}") from exc

    relevant_chunks = [
        ts for ts in timestamps if ts < day_end_ms and ts + CHUNK_SPAN_MS > day_start_ms
    ]
    if not relevant_chunks:
        raise SmardUnavailableError("Kein Datenchunk für dieses Datum verfügbar.")

    points = []
    for chunk_ts in relevant_chunks:
        try:
            points.extend(_fetch_chunk(chunk_ts))
        except requests.RequestException as exc:
            raise SmardUnavailableError(f"SMARD-Daten nicht erreichbar: {exc}") from exc

    hourly_sums = [0.0] * 24
    hourly_counts = [0] * 24
    for ts, price in points:
        if price is None or not (day_start_ms <= ts < day_end_ms):
            continue
        hour = int((ts - day_start_ms) // 3_600_000)
        if 0 <= hour < 24:
            hourly_sums[hour] += price
            hourly_counts[hour] += 1

    if any(count == 0 for count in hourly_counts):
        raise SmardUnavailableError(
            "Für dieses Datum liegen noch nicht alle Stundenpreise vor (Daten evtl. noch nicht veröffentlicht)."
        )

    return [total / count for total, count in zip(hourly_sums, hourly_counts)]
