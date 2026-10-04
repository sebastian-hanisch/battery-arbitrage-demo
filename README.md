# 🔋 Batteriespeicher-Arbitrage

Interaktive Demo zur Batteriespeicher-Arbitrage: Anhand echter deutscher Day-Ahead-Strompreise wird der gewinnmaximale Lade-/Entladeplan für einen Batteriespeicher gesucht — mit möglichst hohem Gewinn.

**[→ Demo live ausprobieren](https://sebastianhanisch-battery-arbitrage-demo.streamlit.app/)**

## Worum geht's?

Die einzige Demo im Portfolio mit einem echten **Lager-/Speicherproblem über die Zeit**: Der Ladezustand entwickelt sich Stunde für Stunde durch die eigenen Lade-/Entladeentscheidungen, statt (wie bei den anderen Demos) eine feste Menge auf feste Ressourcen zu verteilen.

Verglichen wird eine naive "billig laden, teuer entladen"-Heuristik mit der LP-optimalen Lösung, die den ganzen Tag gemeinsam betrachtet. Kernpunkt: Nichtstun (Gewinn 0) ist für die LP immer eine zulässige Option — die LP-Lösung kann also nie schlechter sein. Die naive Heuristik hat diese Garantie nicht und verliert in einem der drei Beispielszenarien tatsächlich Geld.

Strompreise sind echte deutsche Day-Ahead-Preise von [SMARD.de](https://www.smard.de) (Bundesnetzagentur, öffentliche API), stündlich gemittelt aus Viertelstundenwerten — nicht synthetisch erzeugt. Neben den drei fest hinterlegten Beispieltagen kann wahlweise ein beliebiges Datum live von der SMARD-API geladen werden (`battery_data.py`); schlägt der Abruf fehl oder liegen für den Tag noch nicht alle Stundenwerte vor, fällt die Demo automatisch auf einen Beispieltag zurück.

Jede Auswahl (Szenario, Datum, Batterie-Einstellungen) spiegelt sich als Permalink in der URL wider (`battery_permalink.py`) — ein kopierter Link reproduziert exakt denselben Zustand, ganz ohne eigenes Backend oder Session-Storage.

## Methodik

- LP-Modell: SciPy `linprog` (HiGHS), Zustandsgleichung für den Ladezustand über alle 24 Stunden als Nebenbedingungen
- Bei Preisen ab 0 €/MWh braucht es kein Ganzzahligkeitsmodell, um gleichzeitiges Laden und Entladen in derselben Stunde auszuschließen: Der Wirkungsgradverlust macht ein solches Paar nie zu einer echten Verbesserung (Ersatz durch die Nettoaktion bringt p·(1/η − 1)·Entladung ≥ 0 mehr).
- **Bei negativen Preisen gilt das nicht** (ein unabhängiges MILP-Orakel deckte das auf): Ein gleichzeitiges Paar, das den Ladezustand hält, wird dann für die „verbrannte“ Verlustenergie bezahlt — auch bei vollem Speicher, physikalisch nicht betreibbar und im Diagramm (Nettobalken) nicht nachvollziehbar. Taucht so ein Paar in der LP-Lösung auf, löst `lp_optimal` das Problem exakt als kleines MILP (binärer Schalter Laden/Entladen je Stunde). Im Beispieltag „Negative Preise“ sinkt der LP-Bestwert dadurch von 1,8132 € auf 1,8060 €; die anderen beiden Beispieltage sind unverändert.
- Ein Kalendertag wird in deutscher Ortszeit gebildet und hat an den Zeitumstellungstagen 23 Stunden (29.03.2026) bzw. 25 Stunden (25.10.2026); `fetch_day_prices` liefert dann entsprechend viele Preise (früher fiel der 23-Stunden-Tag immer auf den Beispieltag zurück, beim 25-Stunden-Tag fehlte die letzte Stunde). Der Rest der Demo rechnet mit beliebig vielen Stunden.
- Test gegen ein von Hand nachrechenbares Zwei-Stunden-Beispiel (Preise 10 vs. 100 EUR/MWh, perfekter Wirkungsgrad): eindeutig optimal ist voll laden zur billigen und voll entladen zur teuren Stunde
- Regressionstest, der die tatsächliche Ursache eines gefundenen Bugs dokumentiert: Ein naiver Vergleich zwischen LP und Heuristik schlug fehl, weil die Heuristik den Ladezustand am Tagesende unter den Startwert drücken durfte und die LP nicht — kein Solver-Fehler, sondern ein unfairer Vergleich (behoben durch dieselbe End-Ladezustand-Regel für beide)

## Lokal ausführen

```bash
pip install -r requirements-dev.txt
streamlit run app.py
```

Tests: `pytest tests/ -v`

---

Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – Operations Research und Machine Learning ([Über mich](https://sebastianhanisch.net/ueber-mich.html)). Mehr zu den Demos: [Interaktive Demos](https://sebastianhanisch.net/demos.html).
