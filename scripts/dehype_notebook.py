"""Rewrite markdown cells in main.ipynb to sound less AI-generated.
- swap Electron refs for PySide6 desktop-app (post-migration)
- drop hype words (geavanceerd, cruciaal, naadloos)
- replace em-dashes with commas in NL prose
- keep code cells untouched
"""
import json
import pathlib

NB = pathlib.Path("main.ipynb")
nb = json.loads(NB.read_text(encoding="utf-8"))

REPLACEMENTS = [
    # Electron -> PySide6 desktop (markdown + code comments)
    ("Electron desktop-app", "PySide6 desktop-app"),
    ("Electron app", "desktop-app"),
    ("Electron-app", "desktop-app"),
    ("Electron-map", "edge-map"),
    ("Electron", "desktop"),
    ("electron/src/sentiment_lite.json", "models/sentiment_lite.json"),
    ("ELECTRON_SRC = 'electron/src'", "EDGE_DIR = 'models'"),
    ("ELECTRON_SRC", "EDGE_DIR"),
    ("electron/src/", "models/"),
    ("App.jsx", "app/ui.py"),
    ("puur JavaScript", "Python (numpy)"),
    ("scoreLocal() in app/ui.py", "edge-scoring in app/models.py"),
    ("Replica van edge-scoring in app/models.py, TF-IDF + sigmoid in pure Python.",
     "TF-IDF + sigmoid scoring in pure Python."),
    ("in JavaScript doet, in Python,", "doet,"),
    ("Geen netwerk nodig, werkt offline.",
     "Werkt offline zonder netwerk."),
    # hype words
    ("Geavanceerde drift", "Drift op feature-niveau"),
    ("geavanceerd", "uitgebreid"),
    ("cruciaal", "belangrijk"),
    ("naadloos", "zonder gedoe"),
    # em-dash to comma
    ("` — ", "`, "),
    (" — ", ", "),
    # phrasing tells
    ("Daarnaast,", "Verder"),
    ("Daarnaast ", "Verder "),
    ("Tot slot,", "En tot slot,"),
]

changed = 0
for cell in nb["cells"]:
    src = "".join(cell["source"])
    new = src
    for old, repl in REPLACEMENTS:
        new = new.replace(old, repl)
    if new != src:
        cell["source"] = new.splitlines(keepends=True)
        changed += 1

# Cell 45: replace the npm-start hint with PySide6 launch hint
CELL45_OLD_BLOCK = """print('Start de desktop-app vanuit de project-root:')
print('  cd electron && npm install && npm run dev   # browser, dev-server')
print('  cd electron && npm start                     # desktop window')"""
CELL45_NEW_BLOCK = """print('Start de desktop-app vanuit de project-root:')
print('  python app/ui.py              # operator-window')
print('  python app/ui.py --mobile     # beller-window')"""

# Cell 49: replace the electron-file-presence tuple with desktop entrypoints.
# We target the tuple line directly because earlier replacements already
# rewrote some App.jsx -> app/ui.py inside the same line.
CELL49_OLD_TUPLE = "for f in ('run.ps1', 'electron/package.json', 'electron/main.js', 'models/app/ui.py'):"
CELL49_NEW_TUPLE = "for f in ('app/ui.py', 'app/backend.py', 'app/models.py', 'serve.py'):"

CELL49_TAIL_OLD = "start met `pwsh -File run.ps1`."
CELL49_TAIL_NEW = "start met `python app/ui.py`."

for cell in nb["cells"]:
    if cell["cell_type"] != "code":
        continue
    src = "".join(cell["source"])
    new = src.replace(CELL45_OLD_BLOCK, CELL45_NEW_BLOCK)
    new = new.replace(CELL49_OLD_TUPLE, CELL49_NEW_TUPLE)
    new = new.replace(CELL49_TAIL_OLD, CELL49_TAIL_NEW)
    if new != src:
        cell["source"] = new.splitlines(keepends=True)
        changed += 1

# specific rewrite for cell 0 intro paragraph (less marketing-y)
intro_old = "VitaCall is een Nederlandse alarmcentrale. Dit notebook bouwt twee sentiment-classificatiemodellen voor inkomende gesprekken. De zware variant draait achter een FastAPI REST service voor de centrale. De lichte variant zit in een PySide6 desktop-app voor de medewerker en werkt offline."
intro_new = "VitaCall is een Nederlandse alarmcentrale. In dit notebook train ik twee sentiment-modellen voor binnenkomende gesprekken. Het zware model draait achter een FastAPI service. Het lichte model zit in een PySide6 desktop-app en werkt offline."

# specific rewrite for cell 64 conclusion intro
concl_old = "## Conclusie, wat de docent kan afvinken"
concl_new = "## Conclusie"

for cell in nb["cells"]:
    if cell["cell_type"] != "markdown":
        continue
    src = "".join(cell["source"])
    new = src.replace(intro_old, intro_new).replace(concl_old, concl_new)
    if new != src:
        cell["source"] = new.splitlines(keepends=True)
        changed += 1

NB.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"changed_cells={changed}")
