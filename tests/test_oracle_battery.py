"""Unabhängiges Orakel für die Batteriearbitrage: ein MILP in anderer Formulierung (Ladezustand als
eigene Variablen mit Gleichungen, binärer Schalter "laden ODER entladen" je Stunde, mip_rel_gap=0),
das den physikalisch sinnvollen Optimalwert liefert. Es deckte auf, dass das reine LP bei NEGATIVEN
Preisen gleichzeitiges Laden und Entladen als echte Verbesserung nutzt (es "verbrennt" die
Wirkungsgradverlust-Energie gegen Bezahlung) - der frühere Text 'exaktes Unentschieden' galt nur für
Preise >= 0."""

import math
import random

import numpy as np
import pytest

from battery_constants import PRICE_PRESETS
from battery_model import build_problem, is_feasible_schedule
from battery_solver import lp_optimal, naive_heuristic, net_flow

optimize = pytest.importorskip("scipy.optimize")


def _exclusive_optimum(prices, cap, rate, eta, s0):
    """Maximaler Gewinn (EUR) ohne gleichzeitiges Laden und Entladen; Variablen [laden, entladen, SoC, z]."""
    n_h = len(prices)
    p = np.asarray(prices, dtype=float) / 1000.0
    leg = math.sqrt(eta)
    n_var = 2 * n_h + (n_h + 1) + n_h
    soc_at = lambda t: 2 * n_h + t        # noqa: E731
    z_at = lambda t: 3 * n_h + 1 + t      # noqa: E731
    cost = np.zeros(n_var)
    cost[:n_h], cost[n_h:2 * n_h] = p, -p
    rows, lo, hi = [], [], []

    def add(row, low, high):
        rows.append(row)
        lo.append(low)
        hi.append(high)

    row = np.zeros(n_var)
    row[soc_at(0)] = 1
    add(row, s0, s0)
    for t in range(n_h):
        row = np.zeros(n_var)
        row[soc_at(t + 1)], row[soc_at(t)], row[t], row[n_h + t] = 1, -1, -leg, 1 / leg
        add(row, 0, 0)
        row = np.zeros(n_var)
        row[t], row[z_at(t)] = 1, -rate
        add(row, -np.inf, 0)
        row = np.zeros(n_var)
        row[n_h + t], row[z_at(t)] = 1, rate
        add(row, -np.inf, rate)
    row = np.zeros(n_var)
    row[soc_at(n_h)] = 1
    add(row, s0, np.inf)
    integrality = np.zeros(n_var)
    integrality[3 * n_h + 1:] = 1
    upper = np.concatenate([np.full(2 * n_h, rate), np.full(n_h + 1, cap), np.ones(n_h)])
    res = optimize.milp(cost, constraints=optimize.LinearConstraint(np.array(rows), lo, hi), integrality=integrality,
                        bounds=optimize.Bounds(np.zeros(n_var), upper), options={"mip_rel_gap": 0.0})
    assert res.success
    return -res.fun


def test_hand_example_full_battery_at_negative_price():
    # Batterie voll (10 kWh), eta = 0,64 (Teilwirkungsgrad 0,8), Preis -100 EUR/MWh in beiden Stunden.
    # Exklusiv (Handrechnung): Stunde 0 entladen x = 3,2 kWh (kostet 0,32 EUR, SoC -4), Stunde 1 mit der
    # Leistungsgrenze 5 kWh nachladen (bringt 0,50 EUR, SoC +4) -> 0,18 EUR; mehr gibt die Leistungsgrenze nicht her.
    # Gleichzeitig 5 kWh laden + 3,2 kWh entladen hielte den Ladezustand (0,8*5 - 3,2/0,8 = 0) und brächte
    # je Stunde -0,1 * (3,2 - 5) = 0,18 EUR, zusammen 0,36 EUR - physikalisch unmöglich, darf nicht ausgewiesen werden.
    problem = build_problem([-100.0, -100.0], capacity_kwh=10.0, max_rate_kw=5.0, efficiency=0.64, start_soc_kwh=10.0)
    result = lp_optimal(problem)
    assert result.profit == pytest.approx(0.18, abs=1e-9)
    assert not np.any((result.charge > 1e-7) & (result.discharge > 1e-7))
    assert _exclusive_optimum([-100.0, -100.0], 10.0, 5.0, 0.64, 10.0) == pytest.approx(0.18, abs=1e-9)


def test_negative_price_preset_matches_exclusive_optimum_and_chart_is_consistent():
    prices = PRICE_PRESETS["Negative Preise (08.08.2026)"]
    problem = build_problem(prices, capacity_kwh=10.0, max_rate_kw=5.0, efficiency=0.90, start_soc_kwh=5.0)
    result = lp_optimal(problem)
    assert result.profit == pytest.approx(_exclusive_optimum(prices, 10.0, 5.0, 0.90, 5.0), abs=1e-7)
    assert is_feasible_schedule(problem, result.charge, result.discharge)
    assert not np.any((result.charge > 1e-7) & (result.discharge > 1e-7))
    # die im Diagramm gezeigten Nettoflüsse müssen genau den gezeigten Ladezustand erzeugen
    leg, soc = math.sqrt(0.90), [problem.start_soc_kwh]
    for flow in net_flow(result):
        soc.append(soc[-1] + (-flow * leg if flow < 0 else -flow / leg))
    assert np.allclose(soc, result.soc, atol=1e-6)


def test_lp_equals_exclusive_optimum_on_random_instances():
    rng = random.Random(1)
    for _ in range(80):
        n_h = rng.choice([4, 8, 24])
        low = -30.0 if rng.random() < 0.5 else 0.0
        prices = [rng.uniform(low, 250.0) for _ in range(n_h)]
        cap, rate = rng.choice([1.0, 5.0, 10.0, 50.0]), rng.choice([0.5, 2.0, 5.0, 25.0])
        eta = rng.choice([0.5, 0.7, 0.9, 0.99, 1.0])
        s0 = cap * rng.choice([0.0, 0.25, 0.5, 1.0])
        problem = build_problem(prices, cap, rate, eta, s0)
        result = lp_optimal(problem)
        assert is_feasible_schedule(problem, result.charge, result.discharge)
        assert result.profit == pytest.approx(_exclusive_optimum(prices, cap, rate, eta, s0), abs=1e-7)
        naive = naive_heuristic(problem)
        assert is_feasible_schedule(problem, naive.charge, naive.discharge)
        assert naive.profit <= result.profit + 1e-7


# --- Sommerzeit-Umstellungstage in battery_data.fetch_day_prices (Europe/Berlin) ---
# Orakel: feste Kalenderfakten. 2026-03-29 hat 23 Stunden (02:00 -> 03:00 CEST), 2026-10-25 hat
# 25 Stunden (03:00 CEST -> 02:00 CET). Die Viertelstunden-Zeitstempel werden unabhängig in UTC
# aufgebaut (Berlin-Mitternacht = 23:00 UTC bzw. 22:00 UTC am Vortag).


def _dst_day_prices(monkeypatch, day, start_utc, n_hours):
    import datetime

    import battery_data as bd

    bd._fetch_index.clear()
    bd._fetch_chunk.clear()
    bd.fetch_day_prices.clear()
    start_ms = int(start_utc.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
    # Preis = Nummer der vergangenen Stunde (Mittel je Stunde also genau diese Nummer)
    series = [[start_ms + i * 900_000, float(i // 4)] for i in range(n_hours * 4)]
    # Nachbartage liegen im selben Chunk, dürfen aber nicht in den Tag hineinlaufen
    series = [[start_ms - 900_000, 999.0]] + series + [[start_ms + n_hours * 3_600_000, 999.0]]

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    monkeypatch.setattr(
        bd.requests, "get",
        lambda url, timeout: _Resp({"timestamps": [start_ms - 900_000]} if url == bd.SMARD_INDEX_URL else {"series": series}),
    )
    try:
        return bd.fetch_day_prices(day)
    finally:
        bd.fetch_day_prices.clear()


def test_fetch_day_prices_spring_dst_day_has_23_hours(monkeypatch):
    import datetime

    prices = _dst_day_prices(monkeypatch, datetime.date(2026, 3, 29), datetime.datetime(2026, 3, 28, 23, 0), 23)
    assert prices == [float(h) for h in range(23)]


def test_fetch_day_prices_autumn_dst_day_has_25_hours(monkeypatch):
    import datetime

    prices = _dst_day_prices(monkeypatch, datetime.date(2026, 10, 25), datetime.datetime(2026, 10, 24, 22, 0), 25)
    assert prices == [float(h) for h in range(25)]


def test_fetch_day_prices_normal_day_still_24_hours(monkeypatch):
    import datetime

    prices = _dst_day_prices(monkeypatch, datetime.date(2026, 6, 15), datetime.datetime(2026, 6, 14, 22, 0), 24)
    assert prices == [float(h) for h in range(24)]
