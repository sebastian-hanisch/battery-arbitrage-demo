"""Two solution approaches for battery arbitrage, compared head to head:

1. A naive heuristic: charge during the N cheapest hours, discharge during
   the N priciest hours (N chosen greedily from the battery's capacity/rate
   limits), without ever looking at the actual sequence of prices or how the
   state of charge evolves hour by hour.

2. The LP-optimal schedule: a linear program over all 24 charge/discharge
   decisions at once, respecting the battery's capacity, rate limit and
   round-trip efficiency as it evolves hour by hour. No binary "not
   simultaneously" variable is needed to rule out charging and discharging
   in the very same hour: replacing any such pair with a smaller net move
   changes that hour's cash flow by exactly zero (it's a real tie, not a
   strict improvement - only later hours' state of charge can end up higher
   as a side effect). Because it's an exact tie, the LP solver is free to
   return either representation without changing the profit; net_flow()
   below nets them into a single number per hour purely for display, since
   showing simultaneous "buy" and "sell" bars at an identical price is
   confusing even though it's not incorrect.
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

from battery_model import BatteryProblem, profit, simulate_soc


@dataclass
class ScheduleResult:
    charge: np.ndarray
    discharge: np.ndarray
    soc: np.ndarray
    profit: float


def lp_optimal(problem: BatteryProblem) -> ScheduleResult:
    T = problem.n_periods
    leg_eta = problem.leg_efficiency
    prices = problem.prices_per_kwh

    # Variables: x = [charge_0..T-1, discharge_0..T-1]
    n = 2 * T
    c = np.concatenate([prices, -prices])  # minimize cost - revenue = -profit

    bounds = [(0, problem.max_rate_kw)] * n

    rows = []
    rhs = []
    for t in range(1, T + 1):
        # SoC[t] = start + sum_{s<t} (leg_eta*charge_s - discharge_s/leg_eta)
        row = np.zeros(n)
        row[:t] = leg_eta
        row[T:T + t] = -1.0 / leg_eta
        rows.append(row)  # SoC[t] <= capacity
        rhs.append(problem.capacity_kwh - problem.start_soc_kwh)
        rows.append(-row)  # SoC[t] >= 0
        rhs.append(problem.start_soc_kwh)

    # End-of-day SoC must be at least what it started with - otherwise a
    # single day's LP could "cash in" stored energy that was never paid for
    # today, which wouldn't be a repeatable daily strategy.
    end_row = np.zeros(n)
    end_row[:T] = leg_eta
    end_row[T:] = -1.0 / leg_eta
    rows.append(-end_row)
    rhs.append(0.0)

    A_ub = np.array(rows)
    b_ub = np.array(rhs)

    res = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(f"Battery LP failed: {res.message}")

    charge = res.x[:T]
    discharge = res.x[T:]
    soc = simulate_soc(problem, charge, discharge)
    return ScheduleResult(charge=charge, discharge=discharge, soc=soc, profit=-float(res.fun))


def net_flow(result: ScheduleResult) -> np.ndarray:
    """Positive = net discharge (selling), negative = net charge (buying),
    for a single bar per hour in the chart. Display-only: does not change
    profit, feasibility, or the SoC trajectory, which all still come from
    the true (possibly simultaneous) charge/discharge arrays - see the
    module docstring for why netting them is safe to show but not to solve
    with."""
    return result.discharge - result.charge


def naive_heuristic(problem: BatteryProblem) -> ScheduleResult:
    """Charge during the cheapest hours, discharge during the priciest ones -
    picked by price rank alone, then greedily filled up to whatever the
    capacity/rate limits allow in hour order, without ever re-checking
    whether a later, even cheaper/pricier hour might have been a better
    choice once the state of charge is actually tracked. Never discharges
    below the starting state of charge, matching the same "don't end the
    day worse off than you started" rule the LP is held to."""
    T = problem.n_periods
    leg_eta = problem.leg_efficiency
    charge = np.zeros(T)
    discharge = np.zeros(T)
    soc = problem.start_soc_kwh

    order = np.argsort(problem.prices)  # cheapest first
    cheap_hours = set(order[: T // 3])
    expensive_hours = set(order[-(T // 3):])

    for t in range(T):
        if t in cheap_hours:
            room = (problem.capacity_kwh - soc) / leg_eta
            amount = min(problem.max_rate_kw, max(0.0, room))
            charge[t] = amount
            soc += amount * leg_eta
        elif t in expensive_hours:
            available = (soc - problem.start_soc_kwh) * leg_eta
            amount = min(problem.max_rate_kw, max(0.0, available))
            discharge[t] = amount
            soc -= amount / leg_eta

    soc_trajectory = simulate_soc(problem, charge, discharge)
    return ScheduleResult(charge=charge, discharge=discharge, soc=soc_trajectory, profit=profit(problem, charge, discharge))
