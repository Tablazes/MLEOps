"""Correct dataset-size + metric claims to match the actual MANIFEST + cv_scores.
- 110k DBRD (full dump) -> ~22k labeled DBRD reviews (110k incl. unsup)
- ~87% F1 -> 87% acc / 85% F1 (5-fold)
Only touches markdown cells + README. Preserves outputs.
"""
import json
import pathlib

NB = pathlib.Path("main.ipynb")
README = pathlib.Path("README.md")

MD_REPL = [
    ("ongeveer 110.000 boekenrecensies",
     "het labeled deel van DBRD (~22k recensies; 110k incl. unsup)"),
    ("110k recensies past nog ruim in geheugen",
     "22k recensies past ruim in geheugen"),
    ("train op 110k DBRD",
     "train op ~22k labeled DBRD"),
    ("~87% F1 op test-set",
     "87% accuracy / 85% F1 (5-fold CV) op DBRD test-set"),
]

README_REPL = [
    ("110k Nederlandse boekenrecensies (DBRD) als basis",
     "Labeled deel van DBRD (~22k recensies; 110k incl. unsup) als basis"),
    ("~87% F1 op DBRD test-set",
     "87% accuracy / 85% F1 (5-fold CV) op DBRD test-set"),
]

nb = json.loads(NB.read_text(encoding="utf-8"))
md_changed = 0
for c in nb["cells"]:
    if c["cell_type"] != "markdown":
        continue
    src = "".join(c["source"])
    new = src
    for old, repl in MD_REPL:
        new = new.replace(old, repl)
    if new != src:
        c["source"] = new.splitlines(keepends=True)
        md_changed += 1
NB.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")

rtxt = README.read_text(encoding="utf-8")
for old, repl in README_REPL:
    rtxt = rtxt.replace(old, repl)
README.write_text(rtxt, encoding="utf-8")

print(f"md_cells_updated={md_changed}")
