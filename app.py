"""
Batteriespeicher-Arbitrage - interaktive Demo
Sebastian Hanisch - Operations Research und Machine Learning

Anhand echter deutscher Day-Ahead-Strompreise (SMARD.de, Bundesnetzagentur)
wird der gewinnmaximale Lade-/Entladeplan für einen Batteriespeicher gesucht
- verglichen mit einer naiven "lade billig, entlade teuer"-Heuristik ohne
Blick auf den tatsächlichen Ladezustandsverlauf.

Kernpunkt: Weil jeder Lade-/Entladezyklus durch den Wirkungsgradverlust Geld
kostet, lohnt sich gleichzeitiges Laden und Entladen in derselben Stunde nie
- ohne dass dafür eine Ganzzahligkeitsbedingung nötig wäre. Das lineare
Programm ist außerdem beweisbar nie schlechter als Nichtstun (Gewinn 0 ist
immer zulässig) - die naive Heuristik hat diese Garantie nicht und verliert
in einem der Beispielszenarien tatsächlich Geld.

Code-Struktur wie bei den anderen Demos in diesem Workspace: Modell, Solver
und Visualisierung liegen in eigenen battery_*.py-Modulen neben dieser Datei.
"""

import streamlit as st

from battery_constants import (
    DEFAULT_CAPACITY_KWH,
    DEFAULT_EFFICIENCY,
    DEFAULT_MAX_RATE_KW,
    DEFAULT_START_SOC_FRACTION,
    PRICE_PRESETS,
)
from battery_model import build_problem
from battery_solver import lp_optimal, naive_heuristic, net_flow
from battery_visualization import schedule_figure

st.set_page_config(page_title="Batteriespeicher-Arbitrage - Sebastian Hanisch", layout="wide")

st.title("🔋 Batteriespeicher-Arbitrage")
st.markdown(
    """
Interaktive Demo zur **Batteriespeicher-Arbitrage**: Anhand echter deutscher Day-Ahead-Strompreise
wird der gewinnmaximale Lade-/Entladeplan für einen Batteriespeicher gesucht — verglichen mit einer
naiven "billig laden, teuer entladen"-Heuristik. Hintergrund im Expander "Wie funktioniert diese
Demo?" unten sowie formal hergeleitet im Expander "📐 Mathematische Formulierung".
"""
)
st.caption(
    "Strompreise: echte deutsche Day-Ahead-Preise von [SMARD.de](https://www.smard.de) "
    "(Bundesnetzagentur, öffentliche API), stündlich gemittelt aus Viertelstundenwerten."
)

preset_name = st.selectbox("📅 Beispieltag laden", options=list(PRICE_PRESETS.keys()))

with st.sidebar:
    st.header("⚙️ Batterie-Einstellungen")
    capacity = st.slider("Kapazität (kWh)", 1.0, 50.0, DEFAULT_CAPACITY_KWH, step=0.5)
    max_rate = st.slider("Max. Lade-/Entladeleistung (kW)", 0.5, 25.0, DEFAULT_MAX_RATE_KW, step=0.5)
    efficiency = st.slider(
        "Round-Trip-Wirkungsgrad", 0.5, 1.0, DEFAULT_EFFICIENCY, step=0.01,
        help="Anteil der Energie, der nach einem vollen Lade-Entlade-Zyklus noch nutzbar ist. "
             "Reale Batteriespeicher liegen meist zwischen 85 % und 95 %.",
    )
    start_fraction = st.slider("Start-Ladezustand (Anteil der Kapazität)", 0.0, 1.0, DEFAULT_START_SOC_FRACTION, step=0.05)

problem = build_problem(
    PRICE_PRESETS[preset_name], capacity_kwh=capacity, max_rate_kw=max_rate,
    efficiency=efficiency, start_soc_kwh=capacity * start_fraction,
)

with st.spinner("Löse..."):
    lp_result = lp_optimal(problem)
    naive_result = naive_heuristic(problem)

st.markdown("## 🎯 Ergebnis im Vergleich")
m1, m2, m3 = st.columns(3)
m1.metric("Naive Heuristik", f"{naive_result.profit:.2f} €", help="Lädt in den günstigsten, entlädt in den teuersten Stunden des Tages - ohne Rücksicht auf den Ladezustandsverlauf.")
m2.metric("LP-optimal", f"{lp_result.profit:.2f} €", help="Berücksichtigt alle 24 Stunden gemeinsam inkl. Kapazitäts-, Leistungs- und Wirkungsgradgrenzen.")
diff = lp_result.profit - naive_result.profit
m3.metric("Zusätzlicher Gewinn", f"{diff:.2f} €", delta=f"{100 * diff / abs(naive_result.profit):.0f} %" if abs(naive_result.profit) > 1e-6 else None)

if naive_result.profit < 0:
    st.info(
        "In diesem Szenario **verliert** die naive Heuristik sogar Geld — sie zahlt für Lade-/"
        "Entladezyklen, die sich bei diesem Preisverlauf und Wirkungsgrad nicht lohnen. Die "
        "LP-Lösung kann das nicht: Nichtstun (Gewinn 0) ist immer eine zulässige Option, die "
        "LP-Lösung ist also nie schlechter."
    )

tab_lp, tab_naive = st.tabs(["LP-optimal", "Naive Heuristik"])
with tab_lp:
    st.plotly_chart(schedule_figure(problem, net_flow(lp_result), lp_result.soc, "Lade-/Entladeplan (LP-optimal)"), use_container_width=True)
with tab_naive:
    st.plotly_chart(schedule_figure(problem, net_flow(naive_result), naive_result.soc, "Lade-/Entladeplan (naive Heuristik)"), use_container_width=True)

with st.expander("❓ Wie funktioniert diese Demo?"):
    st.markdown(
        """
**Das Problem:** Ein Batteriespeicher kann Strom günstig einkaufen (laden) und teurer verkaufen
(entladen) — begrenzt durch seine Kapazität, seine maximale Lade-/Entladeleistung und den
Wirkungsgradverlust bei jedem Zyklus. Gesucht ist der Lade-/Entladeplan über 24 Stunden, der den
Gewinn maximiert.

**Naive Heuristik:** Sortiert die Stunden nach Preis, lädt in den günstigsten, entlädt in den
teuersten — ohne zu prüfen, ob der Ladezustand das an der jeweiligen Stelle überhaupt hergibt, und
ohne die Reihenfolge der Stunden zu berücksichtigen.

**LP-optimal:** Ein lineares Programm über alle 24 Stunden gleichzeitig, das den Ladezustand
Stunde für Stunde exakt mitführt. Weil jeder Zyklus durch den Wirkungsgradverlust Geld kostet,
lohnt sich gleichzeitiges Laden und Entladen in derselben Stunde nie wirklich besser als eine der
beiden Aktionen allein — die Lösung braucht deshalb keine Ganzzahligkeitsbedingung, um das
auszuschließen, obwohl sie in seltenen Fällen als eine von mehreren gleich guten Darstellungen
auftauchen kann (dann rein optisch zu einer einzigen Nettozahl je Stunde zusammengefasst).
"""
    )

with st.expander("📐 Mathematische Formulierung"):
    st.markdown(
        r"""
**Zustandsgleichung** (Ladezustand $\text{SoC}_t$, Effizienz $\eta$ als $\sqrt{\eta}$ auf beide
Richtungen aufgeteilt):

$$\text{SoC}_{t+1} = \text{SoC}_t + \text{charge}_t \sqrt{\eta} - \frac{\text{discharge}_t}{\sqrt{\eta}}$$

**Optimierungsmodell:**

$$\max \sum_t \text{price}_t \cdot (\text{discharge}_t - \text{charge}_t)$$

unter $0 \leq \text{charge}_t, \text{discharge}_t \leq P_{\max}$, $0 \leq \text{SoC}_t \leq C$ für
alle $t$, sowie $\text{SoC}_T \geq \text{SoC}_0$ (der Speicher darf am Ende des Tages nicht leerer
sein als zu Beginn — sonst würde ein einzelner Tag bereits vorhandene, nicht heute bezahlte Energie
„versilbern", was keine wiederholbare Tagesstrategie wäre).

**Warum reicht ein LP?** Gleichzeitiges Laden und Entladen in derselben Stunde $t$ verändert den
Gewinnbeitrag dieser Stunde exakt um 0 (Preis kürzt sich heraus), erhöht aber nie den Ladezustand
in späteren Stunden. Es ist also bestenfalls neutral, nie eine echte Verbesserung nötig zu
verhindern — eine binäre Variable dafür würde das Problem unnötig zu einem MILP machen.
"""
    )

st.markdown("---")

st.caption(
    "Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – "
    "Operations Research und Machine Learning. Interesse an einer maßgeschneiderten Lösung für "
    "Ihr Unternehmen? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html)"
)
