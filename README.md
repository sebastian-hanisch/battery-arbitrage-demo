# 🔋 Batteriespeicher-Arbitrage

Interaktive Demo zur Batteriespeicher-Arbitrage: Anhand echter deutscher Day-Ahead-Strompreise wird der gewinnmaximale Lade-/Entladeplan für einen Batteriespeicher gesucht — mit möglichst hohem Gewinn.

## Worum geht's?

Die einzige Demo im Portfolio mit einem echten **Lager-/Speicherproblem über die Zeit**: Der Ladezustand entwickelt sich Stunde für Stunde durch die eigenen Lade-/Entladeentscheidungen, statt (wie bei den anderen Demos) eine feste Menge auf feste Ressourcen zu verteilen.

Verglichen wird eine naive "billig laden, teuer entladen"-Heuristik mit der LP-optimalen Lösung, die den ganzen Tag gemeinsam betrachtet. Kernpunkt: Nichtstun (Gewinn 0) ist für die LP immer eine zulässige Option — die LP-Lösung kann also nie schlechter sein. Die naive Heuristik hat diese Garantie nicht und verliert in einem der drei Beispielszenarien tatsächlich Geld.

Strompreise sind echte deutsche Day-Ahead-Preise von [SMARD.de](https://www.smard.de) (Bundesnetzagentur, öffentliche API), stündlich gemittelt aus Viertelstundenwerten — nicht synthetisch erzeugt.

## Methodik

- LP-Modell: SciPy `linprog` (HiGHS), Zustandsgleichung für den Ladezustand über alle 24 Stunden als Nebenbedingungen
- Kein Ganzzahligkeitsmodell nötig, um gleichzeitiges Laden und Entladen in derselben Stunde auszuschließen: Der Wirkungsgradverlust macht das für die LP-Lösung ohnehin nie zu einer echten Verbesserung (nachgewiesen als exaktes Unentschieden, nicht nur als Vermutung — siehe `tests/test_solver.py`)
- Test gegen ein von Hand nachrechenbares Zwei-Stunden-Beispiel (Preise 10 vs. 100 EUR/MWh, perfekter Wirkungsgrad): eindeutig optimal ist voll laden zur billigen und voll entladen zur teuren Stunde
- Regressionstest, der die tatsächliche Ursache eines gefundenen Bugs dokumentiert: Ein naiver Vergleich zwischen LP und Heuristik schlug fehl, weil die Heuristik den Ladezustand am Tagesende unter den Startwert drücken durfte und die LP nicht — kein Solver-Fehler, sondern ein unfairer Vergleich (behoben durch dieselbe End-Ladezustand-Regel für beide)

## Lokal ausführen

```bash
pip install -r requirements-dev.txt
streamlit run app.py
```

Tests: `pytest tests/ -v`

---

Teil des [Operations-Research-Demo-Portfolios](https://sebastianhanisch.net/demos.html) von [Sebastian Hanisch](https://sebastianhanisch.net) — Operations Research und Machine Learning. Interesse an einer maßgeschneiderten Lösung? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html).
