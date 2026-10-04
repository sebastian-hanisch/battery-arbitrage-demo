"""Two solution approaches for battery arbitrage, compared head to head:

1. A naive heuristic: charge during the N cheapest hours, discharge during
   the N priciest hours (N chosen greedily from the battery's capacity/rate
   limits), without ever looking at the actual sequence of prices or how the
   state of charge evolves hour by hour.

2. The optimal schedule: a linear program over all 24 charge/discharge
   decisions at once, respecting the battery's capacity, rate limit and
   round-trip efficiency as it evolves hour by hour. As long as no price is
   negative, no binary "not simultaneously" variable is needed to rule out
   charging and discharging in the very same hour: replacing any such pair
   with the equivalent single net move (same state of charge afterwards)
   changes the hour's cash flow by p * (1/eta - 1) * discharge >= 0 for a
   price p >= 0, so a simultaneous pair is never strictly better (an exact
   tie only for p = 0 or eta = 1), and the LP solver is free to return
   either representation without changing the profit; net_flow() below
   nets them into a single number per hour purely for display.

   With a NEGATIVE price that argument breaks: a simultaneous pair then
   earns |p| * (charge - discharge) and, by discharging exactly the energy
   it takes in, burns the efficiency loss (1 - eta) for money while the
   battery stays full - strictly better than any exclusive schedule, but
   physically impossible (and inconsistent with the netted bars shown in the
   chart). Whenever the LP solution uses such a pair, lp_optimal() therefore
   re-solves the problem as a small MILP with the exclusivity constraint
   (a binary charge/discharge switch per hour), which is the exact optimum
   of the physically meaningful problem.
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

from battery_model import BatteryProblem, profit, simulate_soc


SIMULTANEOUS_TOL = 1e-7  # kWh; below this a charge/discharge value counts as zero


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

    # Only a negative price lets a simultaneous charge+discharge pair beat every exclusive schedule
    # (see module docstring) - then the LP relaxation overstates the achievable profit.
    simultaneous = (charge > SIMULTANEOUS_TOL) & (discharge > SIMULTANEOUS_TOL) & (prices < 0)
    if np.any(simultaneous):
        return _exclusive_milp(problem)

    soc = simulate_soc(problem, charge, discharge)
    return ScheduleResult(charge=charge, discharge=discharge, soc=soc, profit=-float(res.fun))


def _exclusive_milp(problem: BatteryProblem) -> ScheduleResult:
    """Exact optimum with 'never charge and discharge in the same hour': the LP above plus one binary
    switch z_t per hour (charge_t <= P_max * z_t, discharge_t <= P_max * (1 - z_t))."""
    T = problem.n_periods
    leg_eta = problem.leg_efficiency
    prices = problem.prices_per_kwh
    rate = problem.max_rate_kw

    n = 3 * T  # x = [charge_0..T-1, discharge_0..T-1, z_0..T-1]
    c = np.concatenate([prices, -prices, np.zeros(T)])

    rows, lo, hi = [], [], []
    for t in range(1, T + 1):
        row = np.zeros(n)
        row[:t] = leg_eta
        row[T:T + t] = -1.0 / leg_eta
        rows.append(row)  # 0 <= SoC[t] <= capacity
        lo.append(-problem.start_soc_kwh)
        hi.append(problem.capacity_kwh - problem.start_soc_kwh)
    end_row = np.zeros(n)
    end_row[:T] = leg_eta
    end_row[T:2 * T] = -1.0 / leg_eta
    rows.append(end_row)  # SoC[T] >= start
    lo.append(0.0)
    hi.append(np.inf)
    for t in range(T):
        row = np.zeros(n)
        row[t] = 1.0
        row[2 * T + t] = -rate
        rows.append(row)  # charge_t <= P_max * z_t
        lo.append(-np.inf)
        hi.append(0.0)
        row = np.zeros(n)
        row[T + t] = 1.0
        row[2 * T + t] = rate
        rows.append(row)  # discharge_t <= P_max * (1 - z_t)
        lo.append(-np.inf)
        hi.append(rate)

    integrality = np.concatenate([np.zeros(2 * T), np.ones(T)])
    bounds = Bounds(np.zeros(n), np.concatenate([np.full(2 * T, rate), np.ones(T)]))
    res = milp(c, constraints=LinearConstraint(np.array(rows), lo, hi), integrality=integrality,
               bounds=bounds, options={"mip_rel_gap": 0.0})
    if not res.success:
        raise RuntimeError(f"Battery MILP failed: {res.message}")

    switch = res.x[2 * T:] > 0.5
    charge = np.where(switch, res.x[:T], 0.0)
    discharge = np.where(switch, 0.0, res.x[T:2 * T])
    soc = simulate_soc(problem, charge, discharge)
    return ScheduleResult(charge=charge, discharge=discharge, soc=soc, profit=profit(problem, charge, discharge))


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
