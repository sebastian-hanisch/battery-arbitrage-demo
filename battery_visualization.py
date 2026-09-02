"""Plotly figures for the battery arbitrage demo."""

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

PRICE_COLOR = "#35486A"
DISCHARGE_COLOR = "#3E8E86"
CHARGE_COLOR = "#D68A2E"
SOC_COLOR = "#8E3E86"


def schedule_figure(problem, net, soc, title: str) -> go.Figure:
    hours = list(range(problem.n_periods))
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.6, 0.4], vertical_spacing=0.08,
        specs=[[{"secondary_y": True}], [{}]],
        subplot_titles=(title, "Ladezustand (State of Charge)"),
    )

    fig.add_trace(
        go.Scatter(x=hours, y=problem.prices, name="Preis (EUR/MWh)", line=dict(color=PRICE_COLOR, width=2)),
        row=1, col=1, secondary_y=False,
    )
    bar_colors = [DISCHARGE_COLOR if v >= 0 else CHARGE_COLOR for v in net]
    fig.add_trace(
        go.Bar(
            x=hours, y=net, name="Netto Laden(-)/Entladen(+)", marker_color=bar_colors,
            hovertemplate="Stunde %{x}: %{y:.2f} kWh<extra></extra>",
        ),
        row=1, col=1, secondary_y=True,
    )

    fig.add_trace(
        go.Scatter(
            x=list(range(len(soc))), y=soc, name="SoC (kWh)", fill="tozeroy",
            line=dict(color=SOC_COLOR, width=2),
            hovertemplate="Nach Stunde %{x}: %{y:.2f} kWh<extra></extra>",
        ),
        row=2, col=1,
    )
    fig.add_hline(y=problem.capacity_kwh, line_dash="dot", line_color="#9AA6BA", row=2, col=1)

    fig.update_yaxes(title_text="EUR/MWh", row=1, col=1, secondary_y=False, fixedrange=True)
    fig.update_yaxes(title_text="kWh", row=1, col=1, secondary_y=True, fixedrange=True)
    fig.update_yaxes(title_text="kWh", row=2, col=1, fixedrange=True)
    fig.update_xaxes(title_text="Stunde", row=2, col=1, fixedrange=True)
    fig.update_xaxes(fixedrange=True, row=1, col=1)
    fig.update_layout(height=520, margin=dict(l=10, r=10, t=50, b=10), legend=dict(orientation="h", y=-0.15))
    return fig
