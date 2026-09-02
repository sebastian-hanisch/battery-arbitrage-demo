import datetime

import pytest

import battery_data as bd

DAY_MS = 24 * 3600 * 1000
QUARTER_MS = 15 * 60 * 1000


def _clear_caches():
    bd._fetch_index.clear()
    bd._fetch_chunk.clear()
    bd.fetch_day_prices.clear()


@pytest.fixture(autouse=True)
def clear_streamlit_cache():
    _clear_caches()
    yield
    _clear_caches()


def _utc_ms(*, year, month, day, hour=0, minute=0):
    dt = datetime.datetime(year, month, day, hour, minute, tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1000)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fetch_day_prices_averages_quarterhours_to_hourly(monkeypatch):
    # 2026-06-15 is CEST (UTC+2): local midnight is 2026-06-14T22:00 UTC.
    day = datetime.date(2026, 6, 15)
    chunk_ts = _utc_ms(year=2026, month=6, day=14, hour=22)
    day_start_ms, day_end_ms = chunk_ts, chunk_ts + DAY_MS

    series = []
    for i in range(96):
        ts = day_start_ms + i * QUARTER_MS
        hour = i // 4
        series.append([ts, float(hour)])  # price == hour index, so mean per hour == hour

    def fake_get(url, timeout):
        if url == bd.SMARD_INDEX_URL:
            return _FakeResponse({"timestamps": [chunk_ts]})
        assert url == bd.SMARD_CHUNK_URL.format(chunk_ts=chunk_ts)
        return _FakeResponse({"series": series})

    monkeypatch.setattr(bd.requests, "get", fake_get)

    prices = bd.fetch_day_prices(day)
    assert prices == [float(h) for h in range(24)]


def test_fetch_day_prices_raises_when_hour_missing(monkeypatch):
    day = datetime.date(2026, 6, 15)
    chunk_ts = _utc_ms(year=2026, month=6, day=14, hour=22)
    day_start_ms = chunk_ts

    # Only 92 of 96 quarter-hours present -> hour 23 has no data at all.
    series = [
        [day_start_ms + i * QUARTER_MS, 50.0]
        for i in range(92)
    ]

    def fake_get(url, timeout):
        if url == bd.SMARD_INDEX_URL:
            return _FakeResponse({"timestamps": [chunk_ts]})
        return _FakeResponse({"series": series})

    monkeypatch.setattr(bd.requests, "get", fake_get)

    with pytest.raises(bd.SmardUnavailableError):
        bd.fetch_day_prices(day)


def test_fetch_day_prices_raises_when_values_null(monkeypatch):
    day = datetime.date(2026, 6, 15)
    chunk_ts = _utc_ms(year=2026, month=6, day=14, hour=22)
    day_start_ms = chunk_ts

    series = [[day_start_ms + i * QUARTER_MS, None] for i in range(96)]

    def fake_get(url, timeout):
        if url == bd.SMARD_INDEX_URL:
            return _FakeResponse({"timestamps": [chunk_ts]})
        return _FakeResponse({"series": series})

    monkeypatch.setattr(bd.requests, "get", fake_get)

    with pytest.raises(bd.SmardUnavailableError):
        bd.fetch_day_prices(day)


def test_fetch_day_prices_merges_two_overlapping_chunks(monkeypatch):
    """A day's quarter-hours can be split across two weekly chunks near a
    chunk boundary; fetch_day_prices must merge both."""
    day = datetime.date(2026, 6, 15)
    day_start_ms = _utc_ms(year=2026, month=6, day=14, hour=22)
    split = 40  # first 40 quarter-hours in chunk A, rest in chunk B

    chunk_a_ts = day_start_ms - 3 * DAY_MS  # starts well before the day
    chunk_b_ts = day_start_ms + split * QUARTER_MS  # starts mid-day

    series_a = [[day_start_ms + i * QUARTER_MS, float(i // 4)] for i in range(split)]
    series_b = [[day_start_ms + i * QUARTER_MS, float(i // 4)] for i in range(split, 96)]

    def fake_get(url, timeout):
        if url == bd.SMARD_INDEX_URL:
            return _FakeResponse({"timestamps": [chunk_a_ts, chunk_b_ts]})
        if url == bd.SMARD_CHUNK_URL.format(chunk_ts=chunk_a_ts):
            return _FakeResponse({"series": series_a})
        if url == bd.SMARD_CHUNK_URL.format(chunk_ts=chunk_b_ts):
            return _FakeResponse({"series": series_b})
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(bd.requests, "get", fake_get)

    prices = bd.fetch_day_prices(day)
    assert prices == [float(h) for h in range(24)]


def test_available_date_range(monkeypatch):
    earliest_ts = _utc_ms(year=2018, month=10, day=1)
    latest_ts = _utc_ms(year=2026, month=8, day=30)

    def fake_get(url, timeout):
        assert url == bd.SMARD_INDEX_URL
        return _FakeResponse({"timestamps": [earliest_ts, latest_ts]})

    monkeypatch.setattr(bd.requests, "get", fake_get)

    earliest, latest = bd.available_date_range()
    assert earliest == datetime.date(2018, 10, 1)
    assert latest == datetime.datetime.now(tz=bd.BERLIN).date() - datetime.timedelta(days=1)
