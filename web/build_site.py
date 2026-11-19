# -*- coding: utf-8 -*-
"""GitHub Pages용 사이트 폴더 만들기: python web/build_site.py [_site]"""
import glob, io, json, os, shutil, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "_site"))
shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(os.path.join(OUT, "py")); os.makedirs(os.path.join(OUT, "examples"))
for f in ("index.html", "app.js", "worker.js", "style.css"):
    shutil.copy(os.path.join(ROOT, "web", f), OUT)
for f in ("src/GH_AI_builder.py", "tests/ghsim.py", "tests/render/export_tris.py", "tests/check_examples_real.py", "web/sim_web.py"):
    shutil.copy(os.path.join(ROOT, f), os.path.join(OUT, "py"))
shutil.copy(os.path.join(ROOT, "tests", "real_catalog_rhino8.txt"), OUT)
shutil.copy(os.path.join(ROOT, "src", "GH_AI_builder.py"), OUT)  # 빌더 바로 받기 링크용
man = []
for f in sorted(glob.glob(os.path.join(ROOT, "examples", "*.json"))):
    b = os.path.basename(f); shutil.copy(f, os.path.join(OUT, "examples"))
    title = json.load(io.open(f, encoding="utf-8")).get("title", "")
    man.append({"file": b, "name": (b[:2] + " · " + title) if title else b[:-5].replace("_", " ")})
json.dump(man, io.open(os.path.join(OUT, "examples", "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
open(os.path.join(OUT, ".nojekyll"), "w").close()
print("사이트:", OUT, len(man), "예제")
