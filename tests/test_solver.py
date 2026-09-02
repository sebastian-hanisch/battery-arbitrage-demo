import numpy as np

from battery_constants import PRICE_PRESETS
from battery_model import build_problem, is_feasible_schedule
from battery_solver import lp_optimal, naive_heuristic, net_flow


def test_lp_matches_hand_calculated_two_period_optimum():
    # prices [10, 100] EUR/MWh = [0.01, 0.10] EUR/kWh; capacity/rate = 10 kWh,
    # perfect efficiency, start empty. Optimal is unambiguous: charge fully
    # at the cheap hour (cost 10 kWh * 0.01 = 0.10 EUR), discharge fully at
    # the expensive hour (revenue 10 kWh * 0.10 = 1.00 EUR) -> profit 0.90 EUR.
    # No other feasible schedule can beat this: capacity caps how much can be
    # bought cheap, and there are only two hours to place it in.
    problem = build_problem([10, 100], capacity_kwh=10.0, max_rate_kw=10.0, efficiency=1.0, start_soc_kwh=0.0)
    result = lp_optimal(problem)
    assert is_feasible_schedule(problem, result.charge, result.discharge)
    assert abs(result.profit - 0.90) < 1e-6
    assert abs(result.charge[0] - 10.0) < 1e-6
    assert abs(result.discharge[1] - 10.0) < 1e-6


def test_constant_price_gives_zero_profit_with_lossy_efficiency():
    # With any round-trip loss, cycling the battery at a flat price can only
    # lose money - so the optimal schedule is to do nothing.
    problem = build_problem([50.0] * 6, capacity_kwh=10.0, max_rate_kw=5.0, efficiency=0.9, start_soc_kwh=5.0)
    result = lp_optimal(problem)
    assert abs(result.profit) < 1e-6


def test_lower_efficiency_never_increases_profit():
    prices = PRICE_PRESETS["Volatiler Tag (13.08.2026)"]
    high_eta = build_problem(prices, capacity_kwh=10.0, max_rate_kw=5.0, efficiency=0.95, start_soc_kwh=5.0)
    low_eta = build_problem(prices, capacity_kwh=10.0, max_rate_kw=5.0, efficiency=0.75, start_soc_kwh=5.0)
    assert lp_optimal(low_eta).profit <= lp_optimal(high_eta).profit + 1e-9


def test_lp_profit_never_negative():
    # Doing nothing (charge=discharge=0 for every hour) is always a feasible
    # schedule with profit exactly 0, so the LP optimum - which considers
    # that option too - can never be worse. The naive heuristic has no such
    # guarantee (it can and does lose money, see the "Ruhiger Tag" preset).
    for name, prices in PRICE_PRESETS.items():
        problem = build_problem(prices, capacity_kwh=10.0, max_rate_kw=5.0, efficiency=0.90, start_soc_kwh=5.0)
        assert lp_optimal(problem).profit >= -1e-9, name


def test_lp_never_worse_than_naive_heuristic_on_real_price_data():
    for name, prices in PRICE_PRESETS.items():
        problem = build_problem(prices, capacity_kwh=10.0, max_rate_kw=5.0, efficiency=0.90, start_soc_kwh=5.0)
        lp_result = lp_optimal(problem)
        naive_result = naive_heuristic(problem)
        assert is_feasible_schedule(problem, lp_result.charge, lp_result.discharge)
        assert is_feasible_schedule(problem, naive_result.charge, naive_result.discharge)
        assert lp_result.profit >= naive_result.profit - 1e-6, name


def test_net_flow_reproduces_the_same_profit():
    # Simultaneous charge+discharge in the same hour can appear in the raw
    # LP solution (an exact tie among several equally-optimal vertices, see
    # battery_solver's module docstring) - net_flow() collapses each hour to
    # a single buy/sell number for display. Verify that reconstructing
    # profit from the netted numbers matches the original exactly, i.e. the
    # netting really is a like-for-like display simplification.
    for name, prices in PRICE_PRESETS.items():
        problem = build_problem(prices, capacity_kwh=10.0, max_rate_kw=5.0, efficiency=0.90, start_soc_kwh=5.0)
        result = lp_optimal(problem)
        net = net_flow(result)
        reconstructed_profit = float(np.dot(problem.prices_per_kwh, net))
        assert abs(reconstructed_profit - result.profit) < 1e-6, name
