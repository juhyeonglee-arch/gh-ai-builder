# -*- coding: utf-8 -*-
"""자동 시험 한 번에 돌리기 (GitHub Actions와 내 PC 공용).

사용: python tests/ci_run.py [--out 결과폴더] [--no-render]

하는 일
 1. 빌더 순수 로직 시험 (tests/test_logic.py)
 2. 예제 JSON 전부를 Rhino 8 실제 컴포넌트 목록과 맞춰 보기 (이름 오류 0개여야 통과)
 3. 예제 생성 스크립트를 다시 돌려 커밋된 JSON과 똑같은지 보기 (JSON 손수정 방지)
 4. 그래스호퍼 흉내 검사기(ghsim)로 예제 전부 계산 (ERROR 0개, Bake 결과 1개 이상)
 5. 08 타워 간섭 검사 (구조 부재가 유리 선을 뚫지 않아야 통과)
 6. 예제마다 간이 그림 PNG 저장
결과 요약은 <out>/summary.md 에 남고, 하나라도 실패하면 종료 코드 1.
"""
import ast, filecmp, glob, io, json, os, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
EX = os.path.join(ROOT, "examples")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

args = sys.argv[1:]
OUT = os.path.abspath(args[args.index("--out") + 1]) if "--out" in args else os.path.join(ROOT, "ci_out")
RENDER = "--no-render" not in args
os.makedirs(OUT, exist_ok=True)

results = []  # (이름, 통과?, 설명)


def step(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("[통과] " if ok else "[실패] ") + name + (" — " + detail if detail else ""), flush=True)


def py(*a, cwd=None):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return subprocess.run([sys.executable] + list(a), cwd=cwd, capture_output=True, text=True, encoding="utf-8", env=env)


# 1. 순수 로직
r = py(os.path.join(HERE, "test_logic.py"))
step("빌더 로직 시험", r.returncode == 0 and "ALL OK" in r.stdout, (r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout + r.stderr).strip() else "")

# 2. 실제 컴포넌트 이름 검사
import check_examples_real as CR
import GH_AI_builder as B

idx = B.CatalogIndex(CR.load(os.path.join(HERE, "real_catalog_rhino8.txt")))
examples = sorted(glob.glob(os.path.join(EX, "*.json")))
for f in examples:
    g = B.parse_pasted(io.open(f, encoding="utf-8").read())
    if isinstance(g, tuple): g = g[0]
    iss = sorted(set(B.validate_graph(g, idx)))
    step("이름 검사: " + os.path.basename(f), not iss, "; ".join(iss[:5]))

# 3. 생성 스크립트 재현
tmp = tempfile.mkdtemp()
shutil.copytree(os.path.join(EX, "gen"), os.path.join(tmp, "gen"))
for gen in sorted(glob.glob(os.path.join(tmp, "gen", "gen_*.py"))):
    r = py(os.path.basename(gen), cwd=os.path.dirname(gen))
    made = [p for p in glob.glob(os.path.join(tmp, "*.json"))]
    same = r.returncode == 0 and made and all(filecmp.cmp(p, os.path.join(EX, os.path.basename(p)), shallow=False) for p in made)
    step("생성 스크립트 재현: " + os.path.basename(gen), same,
         "" if same else (r.stderr.strip().splitlines() or ["커밋된 JSON과 다름 — 생성 스크립트를 돌려 JSON을 다시 만드세요"])[-1])
    for p in made: os.remove(p)
shutil.rmtree(tmp, ignore_errors=True)

# 4. ghsim 계산 + 6. 간이 그림
import ghsim as S

table = []
for f in examples:
    name = os.path.splitext(os.path.basename(f))[0]
    t = time.time()
    try:
        s = S.Sim(json.load(io.open(f, encoding="utf-8"))).run()
        probs = s.problems(); geo = s.baked()
        errs = [p for p in probs if p.startswith("ERROR")]
        warns = [p for p in probs if p.startswith("WARN")]
        step("검사기 계산: " + name, not errs and len(geo) > 0, "Bake %d개, 경고 %d개%s" % (len(geo), len(warns), (", 오류: " + "; ".join(errs[:3])) if errs else ""))
        png = ""
        if RENDER and geo:
            png = name + ".png"
            S.render(geo, os.path.join(OUT, png), size=(1000, 1000), title=name)
        table.append((name, len(errs), len(warns), len(geo), png, time.time() - t))
        with io.open(os.path.join(OUT, name + "_검사기.txt"), "w", encoding="utf-8") as fo:
            fo.write("\n".join(probs) + "\nbake geometry: %d\n" % len(geo))
    except Exception as e:
        step("검사기 계산: " + name, False, "%s: %s" % (type(e).__name__, e))

# 5. 08 간섭 검사
tower = os.path.join(EX, "08_비틀린다이아그리드타워_v3.json")
if os.path.exists(tower):
    r = py(os.path.join(HERE, "tools", "clash.py"), tower)
    try:
        d = ast.literal_eval(r.stdout.strip().splitlines()[-1])
        worst = min(v for k, v in d.items() if k != "fex")
        step("간섭 검사: 08 타워", worst > 0, "구조 부재와 유리 선 최소 거리 %dmm (%s)" % (worst, ", ".join("%s %d" % kv for kv in d.items())))
    except Exception:
        step("간섭 검사: 08 타워", False, (r.stdout + r.stderr).strip()[-300:])

# 요약
ok = all(r[1] for r in results)
with io.open(os.path.join(OUT, "summary.md"), "w", encoding="utf-8") as fo:
    fo.write("## 자동 시험 결과 (%s) — %s\n\n" % (sys.platform, "모두 통과 ✅" if ok else "실패 있음 ❌"))
    fo.write("| 항목 | 결과 | 설명 |\n|---|---|---|\n")
    for n, o, d in results: fo.write("| %s | %s | %s |\n" % (n, "✅" if o else "❌", d.replace("|", "/")))
    fo.write("\n| 예제 | 오류 | 경고 | Bake 개수 | 시간(초) |\n|---|---|---|---|---|\n")
    for n, e, w, b, _, t in table: fo.write("| %s | %d | %d | %d | %.0f |\n" % (n, e, w, b, t))
print("\n" + ("모두 통과" if ok else "실패 있음") + " — " + os.path.join(OUT, "summary.md"))
sys.exit(0 if ok else 1)
