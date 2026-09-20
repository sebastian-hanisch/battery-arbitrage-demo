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

import battery_data
import battery_permalink as permalink
from battery_constants import (
    DEFAULT_CAPACITY_KWH,
    DEFAULT_EFFICIENCY,
    DEFAULT_MAX_RATE_KW,
    DEFAULT_PRESET,
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

MODE_LABELS = {permalink.MODE_PRESET: "📅 Beispieltag", permalink.MODE_LIVE: "🔴 Live von SMARD.de"}

# Read the current URL's query parameters as defaults, so a shared link
# (or a reload) reproduces the exact state it was copied from. Written back
# further down, once every widget's actual value is known.
query_params = dict(st.query_params)
mode_default = permalink.parse_choice(query_params, permalink.PARAM_MODE, set(MODE_LABELS), permalink.MODE_PRESET)
preset_default = permalink.parse_choice(query_params, permalink.PARAM_PRESET, set(PRICE_PRESETS), DEFAULT_PRESET)
date_default = permalink.parse_date(query_params, permalink.PARAM_DATE)
capacity_default = permalink.parse_float(query_params, permalink.PARAM_CAPACITY, 1.0, 50.0, DEFAULT_CAPACITY_KWH)
max_rate_default = permalink.parse_float(query_params, permalink.PARAM_MAX_RATE, 0.5, 25.0, DEFAULT_MAX_RATE_KW)
efficiency_default = permalink.parse_float(query_params, permalink.PARAM_EFFICIENCY, 0.5, 1.0, DEFAULT_EFFICIENCY)
start_fraction_default = permalink.parse_float(query_params, permalink.PARAM_START_FRACTION, 0.0, 1.0, DEFAULT_START_SOC_FRACTION)

source_mode = st.radio(
    "Strompreise",
    [MODE_LABELS[permalink.MODE_PRESET], MODE_LABELS[permalink.MODE_LIVE]],
    index=list(MODE_LABELS).index(mode_default),
    horizontal=True,
    help="Beispieltage sind fest hinterlegt und funktionieren immer offline. "
         "Bei „Live von SMARD.de“ wird ein beliebiges Datum direkt von der SMARD-API geladen.",
)

preset_name = None
selected_date = None

if source_mode == MODE_LABELS[permalink.MODE_PRESET]:
    preset_options = list(PRICE_PRESETS.keys())
    preset_name = st.selectbox("Beispieltag laden", options=preset_options, index=preset_options.index(preset_default))
    prices = PRICE_PRESETS[preset_name]
    price_source_caption = f"Beispieltag: {preset_name}"
else:
    try:
        min_date, max_date = battery_data.available_date_range()
    except Exception as exc:
        st.error(f"SMARD.de gerade nicht erreichbar ({exc}). Zeige stattdessen den Beispieltag „{DEFAULT_PRESET}“.")
        prices = PRICE_PRESETS[DEFAULT_PRESET]
        price_source_caption = f"Beispieltag (Fallback): {DEFAULT_PRESET}"
    else:
        date_value = date_default if date_default and min_date <= date_default <= max_date else max_date
        selected_date = st.date_input("Datum", value=date_value, min_value=min_date, max_value=max_date)
        try:
            with st.spinner(f"Lade Day-Ahead-Preise für {selected_date} von SMARD.de..."):
                prices = battery_data.fetch_day_prices(selected_date)
        except battery_data.SmardUnavailableError as exc:
            st.warning(f"Preise für {selected_date} nicht verfügbar ({exc}). Zeige stattdessen den Beispieltag „{DEFAULT_PRESET}“.")
            prices = PRICE_PRESETS[DEFAULT_PRESET]
            price_source_caption = f"Beispieltag (Fallback): {DEFAULT_PRESET}"
        else:
            price_source_caption = f"Live von SMARD.de: {selected_date.strftime('%d.%m.%Y')}"

with st.sidebar:
    st.header("⚙️ Batterie-Einstellungen")
    capacity = st.slider("Kapazität (kWh)", 1.0, 50.0, capacity_default, step=0.5)
    max_rate = st.slider("Max. Lade-/Entladeleistung (kW)", 0.5, 25.0, max_rate_default, step=0.5)
    efficiency = st.slider(
        "Round-Trip-Wirkungsgrad", 0.5, 1.0, efficiency_default, step=0.01,
        help="Anteil der Energie, der nach einem vollen Lade-Entlade-Zyklus noch nutzbar ist. "
             "Reale Batteriespeicher liegen meist zwischen 85 % und 95 %.",
    )
    start_fraction = st.slider("Start-Ladezustand (Anteil der Kapazität)", 0.0, 1.0, start_fraction_default, step=0.05)

# Sync the resolved state back into the URL so the address bar is always a
# working permalink for exactly what's currently shown.
st.query_params.clear()
st.query_params.update(permalink.build_params(
    mode=permalink.MODE_LIVE if source_mode == MODE_LABELS[permalink.MODE_LIVE] else permalink.MODE_PRESET,
    preset_name=preset_name, selected_date=selected_date,
    capacity_kwh=capacity, max_rate_kw=max_rate, efficiency=efficiency, start_fraction=start_fraction,
))

st.caption(f"📊 {price_source_caption}")
st.caption("🔗 Permalink: Die URL in der Adresszeile spiegelt genau diese Einstellungen wider und kann geteilt werden.")

problem = build_problem(
    prices, capacity_kwh=capacity, max_rate_kw=max_rate,
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
    st.plotly_chart(schedule_figure(problem, net_flow(lp_result), lp_result.soc, "Lade-/Entladeplan (LP-optimal)"), width="stretch", key="schedule_lp")
with tab_naive:
    st.plotly_chart(schedule_figure(problem, net_flow(naive_result), naive_result.soc, "Lade-/Entladeplan (naive Heuristik)"), width="stretch", key="schedule_naive")

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
**Entscheidungsvariablen** (für jede Stunde $t = 0, \dots, 23$):

| Symbol | Bedeutung |
|---|---|
| $\text{charge}_t \geq 0$ | in Stunde $t$ eingekaufte und eingeladene Energie (kWh) |
| $\text{discharge}_t \geq 0$ | in Stunde $t$ entnommene und verkaufte Energie (kWh) |
| $\text{SoC}_t$ | Ladezustand ("State of Charge") zu Beginn von Stunde $t$ (kWh) |

**Zustandsgleichung — wie sich der Ladezustand von Stunde zu Stunde entwickelt:**

$$\text{SoC}_{t+1} = \text{SoC}_t + \sqrt{\eta} \cdot \text{charge}_t - \frac{1}{\sqrt{\eta}} \cdot \text{discharge}_t$$

Ohne Verluste wäre das schlicht *Ladezustand + Eingeladenes − Ausgeladenes*. Der
Round-Trip-Wirkungsgrad $\eta$ (z. B. 0,90 = 90 %) sagt aber, wie viel der eingeladenen Energie
nach einem vollen Lade-Entlade-Zyklus tatsächlich noch nutzbar ist. Damit dieser eine Verlust
nicht willkürlich nur einer Richtung zugeschlagen wird, verteilt ihn das Modell symmetrisch:
$\sqrt{\eta}$ geht beim Laden "verloren", $\sqrt{\eta}$ nochmal beim Entladen — zusammen ergibt
das für einen kompletten Zyklus wieder genau $\eta$.

**Zielfunktion — Gewinn über alle 24 Stunden maximieren:**

$$\max \sum_{t=0}^{23} \text{price}_t \cdot (\text{discharge}_t - \text{charge}_t)$$

Verkaufserlös minus Einkaufskosten, Stunde für Stunde aufsummiert.

**Nebenbedingungen:**

- $0 \leq \text{charge}_t, \text{discharge}_t \leq P_{\max}$ — die Lade-/Entladeleistung ist durch die Anschlussleistung des Speichers begrenzt.
- $0 \leq \text{SoC}_t \leq C$ für alle $t$ — der Ladezustand darf die Speicherkapazität $C$ nie unter- oder überschreiten.
- $\text{SoC}_{24} \geq \text{SoC}_0$ — am Ende des Tages darf der Speicher nicht leerer sein als zu Beginn. Sonst könnte ein einzelner Tag bereits vorhandene, nicht heute bezahlte Energie „versilbern" — keine wiederholbare Tagesstrategie.

**Warum genügt ein lineares Programm — ganz ohne Ganzzahligkeitsbedingung?**

Man könnte vermuten, es brauche eine zusätzliche Regel, die verhindert, dass $\text{charge}_t$
und $\text{discharge}_t$ in derselben Stunde beide positiv sind — ökonomisch wäre das ja unsinnig.
Nötig ist sie aber nicht: Gleichzeitiges Laden und Entladen in Stunde $t$ verändert den
Gewinnbeitrag dieser Stunde exakt um 0 (der Preis kürzt sich heraus), kann den späteren
Ladezustand gegenüber nur einer der beiden Aktionen aber nie erhöhen. Es ist also bestenfalls
gleichwertig, nie besser — der Solver hat gar keinen Anreiz dazu. Eine binäre Variable, die das
explizit ausschließt, würde das Problem nur unnötig zu einem gemischt-ganzzahligen Programm
(MILP) machen.
"""
    )

st.markdown("---")

st.caption(
    "Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – "
    "Operations Research und Machine Learning. Interesse an einer maßgeschneiderten Lösung für "
    "Ihr Unternehmen? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html)"
)
