import numpy as np

from battery_model import build_problem, is_feasible_schedule, simulate_soc


def test_soc_simulation_basic():
    problem = build_problem([10, 100], capacity_kwh=10.0, max_rate_kw=10.0, efficiency=1.0, start_soc_kwh=0.0)
    charge = np.array([10.0, 0.0])
    discharge = np.array([0.0, 10.0])
    soc = simulate_soc(problem, charge, discharge)
    assert np.allclose(soc, [0.0, 10.0, 0.0])


def test_infeasible_schedule_over_capacity_detected():
    problem = build_problem([10, 100], capacity_kwh=10.0, max_rate_kw=10.0, efficiency=1.0, start_soc_kwh=5.0)
    # Charging 10 on top of a starting 5 kWh would exceed the 10 kWh capacity.
    charge = np.array([10.0, 0.0])
    discharge = np.array([0.0, 0.0])
    assert not is_feasible_schedule(problem, charge, discharge)


def test_feasible_schedule_within_bounds():
    problem = build_problem([10, 100], capacity_kwh=10.0, max_rate_kw=10.0, efficiency=1.0, start_soc_kwh=0.0)
    charge = np.array([10.0, 0.0])
    discharge = np.array([0.0, 10.0])
    assert is_feasible_schedule(problem, charge, discharge)
