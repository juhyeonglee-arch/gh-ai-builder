# -*- coding: utf-8 -*-
"""웹 미리보기용: 브라우저(Pyodide)에서 ghsim으로 정의를 계산하고 three.js가 그릴 배열을 만든다.
반복 부재(blocks)는 원형 삼각형 1벌 + 배치 행렬로 넘겨 브라우저에서 인스턴싱한다."""
import io, json, os, tempfile
import numpy as np
import ghsim as S
import GH_AI_builder as B
from export_tris import tri_face

_IDX = None


def load_catalog(text):
    """tests/real_catalog_rhino8.txt 내용으로 이름 검사용 색인을 만든다."""
    global _IDX
    import check_examples_real as CR
    p = os.path.join(tempfile.gettempdir(), "cat.txt")
    io.open(p, "w", encoding="utf-8").write(text)
    _IDX = B.CatalogIndex(CR.load(p))
    return len(_IDX.by_key)


def _tris(objs):
    """[(형상, 재료)] → {재료: float32 (n×9)}"""
    out = {}
    for x, mat in objs:
        b = out.setdefault(mat or "none", [])
        for f in S.faces_of(x):
            n = len(f)
            if n == 3: b.append(f[None])
            elif n == 4: b.append(f[[[0, 1, 2], [0, 2, 3]]])
            elif n > 4:
                t = tri_face(f)
                if t: b.append(np.asarray(t))
    return {m: np.concatenate(v).astype(np.float32).reshape(-1) for m, v in out.items() if v}


def _lines(objs):
    segs = []
    for x, _ in objs:
        for l in S.lines_of(x):
            l = np.asarray(l, float)
            if len(l) > 1: segs.append(np.stack([l[:-1], l[1:]], 1))
    return np.concatenate(segs).astype(np.float32).reshape(-1) if segs else np.zeros(0, np.float32)


def _raw(text):
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.lower().startswith("json"): t = t[4:]
    return json.loads(t)


def run(text, overrides_json="{}"):
    raw = _raw(text)
    if not isinstance(raw, dict) or "nodes" not in raw: raise ValueError("그래프 JSON이 아니에요 (nodes가 없어요)")
    ov = json.loads(overrides_json or "{}")
    for n in raw.get("nodes", []):
        if n.get("id") in ov:
            c = n.get("component", "")
            if "Number Slider" in c: n["slider"][2] = float(ov[n["id"]])
            elif "Boolean Toggle" in c: n["toggle"] = bool(ov[n["id"]])
    g = B.parse_pasted(json.dumps(raw))
    names = sorted(set(B.validate_graph(g, _IDX))) if _IDX is not None else []
    sim = S.Sim(g).run()

    direct = []
    for nid in B.bake_targets(g):
        mat = sim.nodes[nid].get("material", "")
        for x in sim.items(nid): direct.append((x, mat))
    blocks = []
    for bl in g.get("blocks", []):
        parts = [(x, sim.nodes[pid].get("material", "")) for pid in bl["parts"] for x in sim.items(pid)]
        planes = [p if isinstance(p, S.Plane) else S.Plane.world(p) for p in sim.items(bl["at"])
                  if isinstance(p, S.Plane) or (isinstance(p, np.ndarray) and p.shape == (3,))]
        if not parts or not planes: continue
        M = np.stack([P.matrix() for P in planes]).astype(np.float32)
        blocks.append({"name": bl["name"], "count": len(planes), "n_parts": len(parts), "tris": _tris(parts),
                       "matrices": M.transpose(0, 2, 1).reshape(-1)})  # three.js는 열 우선

    sliders = []
    for n in g.get("nodes", []):
        c = n.get("component", "")
        if "Number Slider" in c:
            sliders.append({"id": n["id"], "name": n.get("nickname") or n["id"], "min": n["slider_min"], "max": n["slider_max"],
                            "value": n["slider_value"], "int": bool(n.get("slider_integer")), "group": n.get("group", "")})
        elif "Boolean Toggle" in c:
            sliders.append({"id": n["id"], "name": n.get("nickname") or n["id"], "toggle": bool(n.get("toggle")), "group": n.get("group", "")})
    return {
        "title": g.get("title", ""), "summary": g.get("summary", ""), "notes": g.get("notes", ""),
        "groups": [{"id": x.get("id"), "label": x.get("label", "")} for x in g.get("groups", [])],
        "problems": sim.problems(), "names": names,
        "bake": len(direct) + sum(b["n_parts"] * b["count"] for b in blocks),
        "nodes": len(g.get("nodes", [])), "wires": len(g.get("wires", [])),
        "sliders": sliders, "meshes": _tris(direct), "lines": _lines(direct),
        "blocks": [{k: b[k] for k in ("name", "count", "tris", "matrices")} for b in blocks],
    }


def run_web(text, overrides_json="{}"):
    """브라우저 워커용: (메타 JSON 문자열, float32 배열 목록). 메타 안의 숫자 i는 배열 목록의 i번째."""
    r = run(text, overrides_json)
    bufs = []

    def ref(a):
        bufs.append(np.ascontiguousarray(a, np.float32)); return len(bufs) - 1

    r["meshes"] = {m: ref(a) for m, a in r["meshes"].items()}
    r["lines"] = ref(r["lines"])
    for b in r["blocks"]:
        b["tris"] = {m: ref(a) for m, a in b["tris"].items()}
        b["matrices"] = ref(b["matrices"])
    return json.dumps(r, ensure_ascii=False), bufs
