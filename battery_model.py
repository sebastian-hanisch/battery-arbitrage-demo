"""Problem representation for battery arbitrage against hourly electricity
prices.

The battery's state of charge (SoC) evolves period by period:

    SoC[t+1] = SoC[t] + charge[t] * sqrt(eta) - discharge[t] / sqrt(eta)

where `eta` is the round-trip efficiency, split evenly (as sqrt(eta)) across
the charge and discharge legs - the standard way to model a single combined
efficiency loss without needing to decide how it splits between the two
directions. `charge[t]` is energy drawn from the grid in period t (kWh, cost
= charge[t] * price[t]); `discharge[t]` is energy delivered to the grid
(kWh, revenue = discharge[t] * price[t]).
"""

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BatteryProblem:
    prices: np.ndarray  # EUR/MWh per hour, shape (T,)
    capacity_kwh: float
    max_rate_kw: float
    efficiency: float  # round-trip, 0 < eta <= 1
    start_soc_kwh: float

    @property
    def n_periods(self) -> int:
        return len(self.prices)

    @property
    def prices_per_kwh(self) -> np.ndarray:
        return self.prices / 1000.0  # EUR/MWh -> EUR/kWh

    @property
    def leg_efficiency(self) -> float:
        """sqrt(eta): applied once on charge-in, once on discharge-out."""
        return math.sqrt(self.efficiency)


def build_problem(
    prices, capacity_kwh: float, max_rate_kw: float, efficiency: float, start_soc_kwh: float,
) -> BatteryProblem:
    return BatteryProblem(
        prices=np.asarray(prices, dtype=float),
        capacity_kwh=capacity_kwh,
        max_rate_kw=max_rate_kw,
        efficiency=efficiency,
        start_soc_kwh=start_soc_kwh,
    )


def simulate_soc(problem: BatteryProblem, charge: np.ndarray, discharge: np.ndarray) -> np.ndarray:
    """Returns the SoC trajectory (length n_periods + 1) for a given
    charge/discharge schedule - used both to check feasibility and to plot."""
    leg_eta = problem.leg_efficiency
    soc = np.empty(problem.n_periods + 1)
    soc[0] = problem.start_soc_kwh
    for t in range(problem.n_periods):
        soc[t + 1] = soc[t] + charge[t] * leg_eta - discharge[t] / leg_eta
    return soc


def profit(problem: BatteryProblem, charge: np.ndarray, discharge: np.ndarray) -> float:
    return float(np.dot(problem.prices_per_kwh, discharge - charge))


def is_feasible_schedule(problem: BatteryProblem, charge: np.ndarray, discharge: np.ndarray, tol: float = 1e-6) -> bool:
    if np.any(charge < -tol) or np.any(discharge < -tol):
        return False
    if np.any(charge > problem.max_rate_kw + tol) or np.any(discharge > problem.max_rate_kw + tol):
        return False
    soc = simulate_soc(problem, charge, discharge)
    if not (np.all(soc >= -tol) and np.all(soc <= problem.capacity_kwh + tol)):
        return False
    # A schedule may not end with less energy stored than it started with -
    # otherwise a single day's schedule could "cash in" stored energy that
    # was never paid for today, which isn't a repeatable daily strategy.
    return bool(soc[-1] >= problem.start_soc_kwh - tol)
