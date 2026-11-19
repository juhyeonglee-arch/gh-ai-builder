#! python3
# -*- coding: utf-8 -*-
"""
GH AI 빌더 (Rhino 8)
말로 적은 요청 → 그래스호퍼 캔버스에 진짜 컴포넌트가 선으로 이어진 정의를 만든다.

실행: Rhino 명령창에 RunPythonScript → 이 파일 선택.
구조:
  1) 설치된 그래스호퍼 컴포넌트 목록(입력·출력 이름 포함)을 직접 읽어 '카탈로그'로 만든다.
  2) 카탈로그 + 요청을 Claude API에 보내 JSON 그래프(노드·선·그룹)를 받는다.
  3) 그래스호퍼 SDK로 그 노드를 실제로 만들고, 잇고, 그룹·설명 패널을 단다.
  4) 한 번 계산해 보고 오류가 있으면 오류 내용을 다시 보내 자동으로 고친다(최대 2번).
"""

import json
import os
import io
import re
import threading
import traceback

VERSION = "0.9"
MODEL = "claude-opus-5-5"
EFFORT = "medium"
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2026-10-21"
API_BETA = "server-side-fallback-2026-07-01"
MAX_FIX_ROUNDS = 2

CATEGORIES = ["Params", "Maths", "Sets", "Vector", "Curve", "Surface",
              "Mesh", "Intersect", "Transform", "Display"]

# 손으로 설정해야 제대로 쓰이는 것, 스크립트, 파일 입출력은 뺀다.
EXCLUDE_KEYS = set([
    "Params/Input/Value List", "Params/Input/Graph Mapper", "Params/Input/MD Slider",
    "Params/Input/Control Knob", "Params/Input/Digit Scroller", "Params/Input/Image Sampler",
    "Params/Input/Data Input", "Params/Input/Import 3DM", "Params/Input/Import Image",
    "Params/Input/Import PDB", "Params/Input/Import SHP", "Params/Input/Import Coordinates",
    "Params/Input/Read File", "Params/Input/Atom Data", "Params/Input/Object Details",
    "Params/Input/Button", "Params/Input/Colour Picker", "Params/Input/Colour Wheel",
    "Params/Input/Calendar", "Params/Input/Clock", "Params/Input/Gradient",
    "Params/Util/Data Recorder", "Params/Util/Data Output", "Params/Util/Cluster Input",
    "Params/Util/Cluster Output", "Params/Util/Fitness Landscape", "Params/Util/Galapagos",
    "Params/Util/Timer", "Params/Util/Gene Pool", "Params/Util/Context Bake",
    "Params/Util/Context Print", "Maths/Script/Expression",
])
EXCLUDE_SUBCATS = set(["Maths/Script"])
KEEP_IN_EXCLUDED_SUBCATS = set(["Maths/Script/Evaluate"])

SLIDER_KEY = "Params/Input/Number Slider"
PANEL_KEY = "Params/Input/Panel"
TOGGLE_KEY = "Params/Input/Boolean Toggle"

PRESETS = [
    ("직접 적기", ""),
    ("세로 루버 (각도 변화)",
     "길이 6m, 높이 3m인 벽 앞에 세로 루버를 붙여 줘. 루버 간격·폭·두께는 슬라이더로 조절하고, "
     "루버 각도는 한쪽 끝 0도에서 반대쪽 끝 60도까지 서서히 변하게 해 줘."),
    ("콘타 모형 (등고 판 적층)",
     "가로세로 60m인 완만한 언덕 곡면을 만들고, 1.5m 간격 등고선을 따라 두께 1.5m 판을 쌓아 "
     "콘타 모형처럼 보여 줘. 판 윤곽선은 레이저용으로 바닥에 나란히 펼쳐서도 보여 줘."),
    ("벽돌 쌓기 (회전 패턴)",
     "곡선 벽을 따라 벽돌(230×110×70mm)을 한 단마다 반 장씩 엇갈려 쌓고, "
     "높이가 올라갈수록 벽돌이 조금씩 회전해서 벽면에 패턴이 생기게 해 줘."),
    ("와플 구조 (판재 끼움)",
     "10×6×4m 박스 볼륨을 X, Y 두 방향 판재로 잘라 서로 끼우는 와플 격자를 만들어 줘. "
     "판 간격과 판 두께는 슬라이더로 조절하게 해 줘."),
    ("서까래 (처마 앙곡)",
     "길이 8m 처마선을 따라 서까래를 일정한 간격으로 놓고, 양 끝으로 갈수록 서까래 끝이 "
     "살짝 들리게(한옥 처마 앙곡처럼) 해 줘. 서까래 단면은 원형이고 지름은 슬라이더로."),
]

SYSTEM_RULES = u"""You design Grasshopper (Rhino 8) definitions for an architecture student. You output a JSON graph; a script instantiates it as native Grasshopper components wired on the canvas.

Rules
1. "component" must be an exact key from the CATALOG below (Category/SubCategory/Name). Never invent components. No script components, no plugins.
2. Every value a designer would want to tweak becomes a "Params/Input/Number Slider" with sensible slider_min / slider_max / slider_value in the model units given by the user message, and a short Korean nickname (e.g. "루버 간격"). Whole numbers (counts) → slider_integer true. Fixed text or short number lists → "Params/Input/Panel" with "text" (one item per line). On/off → "Params/Input/Boolean Toggle".
3. If the request needs geometry picked in Rhino (e.g. a site curve), place a matching container (e.g. "Params/Geometry/Curve") with a Korean nickname such as "대지 경계 (Rhino에서 지정)" and say so in notes. Otherwise build the base geometry procedurally so the definition works immediately with no input.
4. Wires: from_output / to_input are parameter Names exactly as listed in the catalog. For parameter objects (sliders, panels, toggles, containers) use "" — they are their own output and input. An input may receive several wires.
5. Data trees matter. Decide list matching deliberately. Set "mapping" on a wire to "graft" when the target input must be grafted (one branch per item, e.g. to make every-to-every combinations or keep members separate), "flatten" to merge branches, otherwise "none". Do not over-graft.
6. Groups: 3–7 groups in the order the algorithm flows (inputs → base geometry → logic → tectonic members → output). Korean labels, short and numbered ("1. 입력 값"). note = one Korean sentence on what the step does and why. Every node belongs to a group.
7. Node ids are short ASCII ("n1", "n2", …). Unused fields: slider_* = 0 / false, text = "", toggle = false.
   bake = true on the 1–3 components whose first output is the final geometry the designer will take into Rhino (e.g. the finished members, the wall surface). False elsewhere.
   material on bake nodes: steel, concrete, glass, aluminum, spandrel, wood or stone ("" elsewhere).
8. Keep it lean: the smallest clear graph that does the job, typically 10–45 nodes. Prefer one robust method over clever tricks. Avoid components whose behaviour depends on settings you cannot set through inputs.
9. Think tectonically: members, layers, joints, thickness, spacing. When the request implies physical elements give them real thickness (Extrude, Box, Pipe, Offset + Cap Holes). For laser-cut sheets output planar closed curves.
10. summary: 3–5 Korean sentences explaining the algorithm's logic to a student. notes: Korean, how to use it (which sliders matter, what to set from Rhino, what to bake).
11. Repeated identical elements (curtain-wall units, bolts, plates, nodes, fins): model ONE prototype at the world origin and compute a list of target planes, then add a "blocks" entry {name, parts: [prototype node ids, each with a material], at: node id whose first output is the planes}. The builder bakes them as Rhino block instances (small files). Otherwise "blocks": [].
12. When you receive an existing definition to edit or fix: keep node ids, nicknames and slider values of unchanged parts; change only what is needed; return the complete new graph.

CATALOG format: key :: description | IN: Name[NickName] Type | OUT: ...   (Type[] = list access, Type{} = tree access). "PARAM" entries are parameter objects with no separate inputs/outputs.
"""

GRAPH_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["title", "summary", "groups", "nodes", "wires", "notes", "blocks"],
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "groups": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["id", "label", "note"],
            "properties": {"id": {"type": "string"}, "label": {"type": "string"},
                           "note": {"type": "string"}}}},
        "nodes": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["id", "component", "group", "nickname", "slider_min", "slider_max",
                         "slider_value", "slider_integer", "text", "toggle", "bake", "material"],
            "properties": {
                "id": {"type": "string"}, "component": {"type": "string"},
                "group": {"type": "string"}, "nickname": {"type": "string"},
                "slider_min": {"type": "number"}, "slider_max": {"type": "number"},
                "slider_value": {"type": "number"}, "slider_integer": {"type": "boolean"},
                "text": {"type": "string"}, "toggle": {"type": "boolean"},
                "bake": {"type": "boolean"},
                "material": {"type": "string", "enum": ["", "steel", "concrete", "glass", "aluminum",
                                                         "spandrel", "wood", "stone"]}}}},
        "wires": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["from_node", "from_output", "to_node", "to_input", "mapping"],
            "properties": {
                "from_node": {"type": "string"}, "from_output": {"type": "string"},
                "to_node": {"type": "string"}, "to_input": {"type": "string"},
                "mapping": {"type": "string", "enum": ["none", "graft", "flatten"]}}}},
        "notes": {"type": "string"},
        "blocks": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "parts", "at"],
            "properties": {"name": {"type": "string"},
                           "parts": {"type": "array", "items": {"type": "string"}},
                           "at": {"type": "string"}}}},
    },
}


# =====================================================================
# 순수 로직 (Rhino 없이 시험 가능)
# =====================================================================

def catalog_line(e):
    def fmt(p):
        name, nick, typ, acc = p
        suf = "[]" if acc == "list" else ("{}" if acc == "tree" else "")
        return "%s[%s] %s%s" % (name, nick, typ, suf)
    desc = (e.get("desc") or "").strip().replace("\n", " ")
    if len(desc) > 60:
        desc = desc[:57] + "..."
    if e["kind"] == "param":
        return "%s :: %s | PARAM" % (e["key"], desc)
    return "%s :: %s | IN: %s | OUT: %s" % (
        e["key"], desc,
        ", ".join(fmt(p) for p in e["inputs"]) or "-",
        ", ".join(fmt(p) for p in e["outputs"]) or "-")


def catalog_text(entries):
    return "\n".join(catalog_line(e) for e in sorted(entries, key=lambda x: x["key"]))


class CatalogIndex(object):
    def __init__(self, entries):
        self.by_key = {}
        self.by_lower = {}
        self.by_name = {}
        for e in entries:
            self.by_key[e["key"]] = e
            self.by_lower[e["key"].lower()] = e
            name = e["key"].split("/")[-1].lower()
            self.by_name.setdefault(name, []).append(e)

    def resolve(self, key):
        if not key:
            return None
        if key in self.by_key:
            return self.by_key[key]
        k = key.strip().lower()
        if k in self.by_lower:
            return self.by_lower[k]
        cands = self.by_name.get(k.split("/")[-1].strip(), [])
        if len(cands) == 1:
            return cands[0]
        return None


def _norm(s):
    return re.sub(r"[\s_\-]", "", (s or "")).lower()


def match_param(params, ref):
    """params: [(name, nick, ...)] → index or None"""
    if not params:
        return None
    ref = ref or ""
    if ref == "" and len(params) == 1:
        return 0
    for i, p in enumerate(params):
        if p[0] == ref:
            return i
    for i, p in enumerate(params):
        if p[1] == ref:
            return i
    r = _norm(ref)
    for i, p in enumerate(params):
        if _norm(p[0]) == r or _norm(p[1]) == r:
            return i
    if ref.strip().isdigit():
        i = int(ref.strip())
        if 0 <= i < len(params):
            return i
    if len(params) == 1:
        return 0
    return None


def sanitize_slider(n):
    mn = float(n.get("slider_min", 0) or 0)
    mx = float(n.get("slider_max", 0) or 0)
    v = float(n.get("slider_value", 0) or 0)
    integer = bool(n.get("slider_integer"))
    if mx < mn:
        mn, mx = mx, mn
    if mx == mn:
        mx = mn + (10 if mn == 0 else abs(mn))
    v = min(max(v, mn), mx)
    if integer:
        mn, mx, v = round(mn), round(mx), round(v)
        if mx == mn:
            mx = mn + 1
        decimals = 0
    else:
        span = mx - mn
        decimals = 3 if span <= 2 else (2 if span <= 50 else (1 if span <= 5000 else 0))
    return mn, mx, v, integer, decimals


NODE_DEFAULTS = {"group": "", "nickname": "", "slider_min": 0, "slider_max": 0, "slider_value": 0,
                 "slider_integer": False, "text": "", "toggle": False, "bake": False,
                 "material": "", "preview": False}


def normalize_graph(g):
    """붙여 넣은 JSON처럼 빠진 칸이 있어도 기본값으로 채운다."""
    g = dict(g)
    for k, v in (("title", ""), ("summary", ""), ("notes", "")):
        g.setdefault(k, v)
    g["groups"] = [dict({"label": x.get("id", ""), "note": ""}, **x) for x in g.get("groups", [])]
    nodes = []
    for n in g.get("nodes", []):
        m = dict(NODE_DEFAULTS)
        m.update(n)
        if "slider" in n and isinstance(n["slider"], list):   # 줄임 표기 [min, max, value]
            m["slider_min"], m["slider_max"], m["slider_value"] = n["slider"][:3]
        if "int" in n:
            m["slider_integer"] = bool(n["int"])
        nodes.append(m)
    g["nodes"] = nodes
    wires = []
    for w in g.get("wires", []):
        if isinstance(w, list):   # 줄임 표기 ["n1", "", "n3", "Length"(, "graft")]
            w = {"from_node": w[0], "from_output": w[1], "to_node": w[2], "to_input": w[3],
                 "mapping": w[4] if len(w) > 4 else "none"}
        w = dict({"from_output": "", "to_input": "", "mapping": "none"}, **w)
        wires.append(w)
    g["wires"] = wires
    g["blocks"] = [dict({"name": "block", "parts": [], "at": ""}, **b) for b in g.get("blocks", [])]
    return g


def parse_pasted(text):
    """요청 칸에 JSON을 붙여 넣었으면 그래프로, 아니면 None."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    t = t.strip()
    if not t.startswith("{"):
        return None
    return normalize_graph(json.loads(t))


PARAM_PREFIX = "Params/"

# 재료: 레이어 이름, 색(RGB), 투명도, 반사
MATERIALS = {
    "steel":    (u"강철", (70, 74, 80), 0.0, 0.35),
    "concrete": (u"콘크리트", (190, 188, 182), 0.0, 0.05),
    "glass":    (u"유리", (150, 190, 215), 0.6, 0.5),
    "aluminum": (u"알루미늄", (175, 180, 186), 0.0, 0.45),
    "spandrel": (u"스팬드럴", (40, 48, 58), 0.0, 0.3),
    "wood":     (u"목재", (176, 128, 82), 0.0, 0.05),
    "stone":    (u"석재", (205, 198, 185), 0.0, 0.08),
}
MATERIAL_ALIASES = {u"강철": "steel", u"철골": "steel", u"콘크리트": "concrete", u"유리": "glass",
                    u"알루미늄": "aluminum", u"스팬드럴": "spandrel", u"목재": "wood", u"나무": "wood",
                    u"석재": "stone", u"돌": "stone"}


def material_for(name):
    k = (name or "").strip()
    k = MATERIAL_ALIASES.get(k, k.lower())
    return k if k in MATERIALS else None


def bake_targets(graph):
    """Bake할 노드: bake 표시가 있으면 그것, 없으면 선이 나가지 않는 마지막 컴포넌트들."""
    in_block = set()
    for b in graph.get("blocks", []):
        in_block.update(b.get("parts", []))
        in_block.add(b.get("at"))
    marked = [n["id"] for n in graph.get("nodes", []) if n.get("bake") and n["id"] not in in_block]
    if marked or in_block:
        return marked
    has_out = set(w["from_node"] for w in graph.get("wires", []))
    has_in = set(w["to_node"] for w in graph.get("wires", []))
    return [n["id"] for n in graph.get("nodes", [])
            if n["id"] not in has_out and n["id"] in has_in
            and not (n.get("component") or "").startswith(PARAM_PREFIX)]


def safe_layer_name(t):
    t = re.sub(r"[\[\]{}():;,/\\]", " ", t or "").strip()
    t = re.sub(r"\s+", " ", t)
    return (t or "GH")[:60]


def validate_graph(graph, index):
    """그래프를 짓기 전에 잘못된 키·이름을 찾는다. → 문제 문자열 목록"""
    issues = []
    nodes = {}
    for n in graph.get("nodes", []):
        if n["id"] in nodes:
            issues.append("duplicate node id %s" % n["id"])
        e = index.resolve(n.get("component"))
        if e is None:
            issues.append("node %s: unknown component '%s'" % (n["id"], n.get("component")))
        nodes[n["id"]] = e
    for bl in graph.get("blocks", []):
        for pid in list(bl.get("parts", [])) + [bl.get("at")]:
            if pid not in nodes:
                issues.append("block %s: node %s missing" % (bl.get("name"), pid))
    for w in graph.get("wires", []):
        a, b = w.get("from_node"), w.get("to_node")
        if a not in nodes or b not in nodes:
            issues.append("wire %s→%s: node missing" % (a, b))
            continue
        ea, eb = nodes[a], nodes[b]
        if ea is not None and ea["kind"] == "component":
            if match_param(ea["outputs"], w.get("from_output")) is None:
                issues.append("node %s (%s): no output named '%s' (has: %s)" % (
                    a, ea["key"], w.get("from_output"), ", ".join(p[0] for p in ea["outputs"])))
        if eb is not None and eb["kind"] == "component":
            if match_param(eb["inputs"], w.get("to_input")) is None:
                issues.append("node %s (%s): no input named '%s' (has: %s)" % (
                    b, eb["key"], w.get("to_input"), ", ".join(p[0] for p in eb["inputs"])))
    return issues


def _layers(ids, edges):
    layer = dict((i, 0) for i in ids)
    for _ in range(len(ids) + 1):
        changed = False
        for a, b in edges:
            if a in layer and b in layer and layer[b] < layer[a] + 1 and layer[a] + 1 <= len(ids):
                layer[b] = layer[a] + 1
                changed = True
        if not changed:
            break
    return layer


def layout_positions(graph, sizes, origin, col_gap=50, row_gap=18, block_gap=110,
                     wrap_width=4200, row_spacing=220):
    """그룹을 왼→오 블록으로 놓고(너무 길면 다음 줄로), 블록 안에서 흐름 순서대로 열을 만든다.
    sizes: id → (w, h). 반환: id → (x, y) 왼쪽 위 좌표."""
    ox, oy = origin
    group_order = [g["id"] for g in graph.get("groups", [])]
    members = {}
    for n in graph["nodes"]:
        if n["id"] not in sizes:
            continue
        g = n.get("group")
        if g not in group_order:
            g = "__etc"
            if g not in group_order:
                group_order.append(g)
        members.setdefault(g, []).append(n["id"])
    edges = [(w["from_node"], w["to_node"]) for w in graph.get("wires", [])]
    pos = {}
    x, top, row_bottom = ox, oy, oy
    for g in group_order:
        ids = members.get(g, [])
        if not ids:
            continue
        idset = set(ids)
        inner = [(a, b) for a, b in edges if a in idset and b in idset]
        layer = _layers(ids, inner)
        cols = {}
        for i in ids:
            cols.setdefault(layer[i], []).append(i)
        block_w = sum(max(sizes[i][0] for i in cols[c]) + col_gap for c in cols)
        if x > ox and x + block_w - ox > wrap_width:
            x, top = ox, row_bottom + row_spacing
        for c in sorted(cols):
            col = cols[c]

            def bary(i):
                ys = [pos[a][1] for a, b in edges if b == i and a in pos]
                return sum(ys) / len(ys) if ys else ids.index(i) * 1e-3 - 1e6

            col.sort(key=bary)
            w = max(sizes[i][0] for i in col)
            y = top
            for i in col:
                pos[i] = (x + (w - sizes[i][0]), y)  # 오른쪽 정렬 → 선이 짧아진다
                y += sizes[i][1] + row_gap
            row_bottom = max(row_bottom, y)
            x += w + col_gap
        x += block_gap
    return pos


def build_user_message(request, units, current_graph=None, issues=None):
    parts = ["Model units: %s. Give slider ranges and dimensions in these units." % units]
    if current_graph is not None:
        parts.append("CURRENT DEFINITION (JSON):\n" + json.dumps(current_graph, ensure_ascii=False))
    if issues:
        parts.append("PROBLEMS FOUND WHEN BUILDING / RUNNING THE CURRENT DEFINITION:\n- " +
                     "\n- ".join(issues) +
                     "\nFix these problems and return the complete corrected graph.")
    if request:
        label = "EDIT REQUEST" if current_graph is not None and not issues else "REQUEST"
        parts.append("%s (Korean):\n%s" % (label, request))
    return "\n\n".join(parts)


def build_request_body(catalog_txt, user_msg, stream=True):
    return {
        "model": MODEL,
        "max_tokens": 64000,
        "stream": stream,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": EFFORT,
                          "format": {"type": "json_schema", "schema": GRAPH_SCHEMA}},
        "fallbacks": "default",
        "system": [{"type": "text", "text": SYSTEM_RULES + "\nCATALOG\n" + catalog_txt,
                    "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user_msg}],
    }


class StreamCollector(object):
    """SSE 'data:' 줄을 받아 글 조각을 모은다."""
    def __init__(self):
        self.text = []
        self.stop_reason = None
        self.error = None
        self.model = None
        self.chars = 0
        self.thinking = False
        self.usage = {}

    def feed(self, line):
        if not line.startswith("data:"):
            return
        data = line[5:].strip()
        if not data:
            return
        ev = json.loads(data)
        t = ev.get("type")
        if t == "message_start":
            self.model = ev.get("message", {}).get("model")
            self.usage.update(ev.get("message", {}).get("usage") or {})
        elif t == "content_block_start":
            self.thinking = ev.get("content_block", {}).get("type") == "thinking"
        elif t == "content_block_delta":
            d = ev.get("delta", {})
            if d.get("type") == "text_delta":
                self.text.append(d.get("text", ""))
                self.chars += len(d.get("text", ""))
        elif t == "message_delta":
            sr = ev.get("delta", {}).get("stop_reason")
            if sr:
                self.stop_reason = sr
            self.usage.update(ev.get("usage") or {})
        elif t == "error":
            self.error = ev.get("error", {}).get("message") or str(ev)

    def result(self):
        if self.error:
            raise RuntimeError("API 오류: " + self.error)
        if self.stop_reason == "refusal":
            raise RuntimeError("모델이 이 요청을 거절했어요. 표현을 바꿔 다시 시도해 주세요.")
        if self.stop_reason == "max_tokens":
            raise RuntimeError("응답이 너무 길어 잘렸어요. 요청을 더 작게 나눠 주세요.")
        txt = "".join(self.text).strip()
        if not txt:
            raise RuntimeError("빈 응답을 받았어요.")
        return json.loads(txt)


# =====================================================================
# Rhino / Grasshopper 부분
# =====================================================================

try:
    import clr
    clr.AddReference("Grasshopper")
    clr.AddReference("System.Drawing")
    import System
    import System.Drawing as SD
    import Rhino
    import scriptcontext as sc
    import Grasshopper
    import Grasshopper.Kernel as GK
    import Eto.Forms as forms
    import Eto.Drawing as drawing
    IN_RHINO = True
except Exception:
    IN_RHINO = False


def unwrap(o):
    """pythonnet 3은 인터페이스 형으로 감싸서 돌려주므로 실제 객체를 꺼낸다."""
    return getattr(o, "__implementation__", o) if o is not None else None


def app_dir():
    d = os.path.join(str(System.Environment.GetFolderPath(
        System.Environment.SpecialFolder.ApplicationData)), "GH_AI")
    if not os.path.isdir(d):
        os.makedirs(d)
    return d


def load_key():
    k = os.environ.get("ANTHROPIC_API_KEY")
    if k:
        return k.strip()
    p = os.path.join(app_dir(), "api_key.txt")
    if os.path.isfile(p):
        with io.open(p, encoding="utf-8") as f:
            return f.read().strip()
    return ""


def save_key(k):
    with io.open(os.path.join(app_dir(), "api_key.txt"), "w", encoding="utf-8") as f:
        f.write(k.strip())


def ensure_gh_doc():
    gh = Rhino.RhinoApp.GetPlugInObject("Grasshopper")
    if gh is not None and not gh.IsEditorLoaded():
        gh.LoadEditor()
    if gh is not None:
        gh.ShowEditor()
    canvas = Grasshopper.Instances.ActiveCanvas
    if canvas is None:
        raise RuntimeError("그래스호퍼 창을 열 수 없어요. Grasshopper 명령으로 먼저 열어 주세요.")
    doc = canvas.Document
    if doc is None:
        doc = GK.GH_Document()
        Grasshopper.Instances.DocumentServer.AddDocument(doc)
        canvas.Document = doc
    return canvas, doc


def _params(plist):
    out = []
    for p in plist:
        out.append([str(p.Name), str(p.NickName), str(p.TypeName), str(p.Access).lower()])
    return out


def build_catalog(log):
    try:
        ver = str(Grasshopper.Versioning.Version)
    except Exception:
        ver = "x"
    proxies = list(Grasshopper.Instances.ComponentServer.ObjectProxies)
    cache = os.path.join(app_dir(), "catalog_%s_%d.json" % (re.sub(r"[^0-9A-Za-z]", "_", ver), len(proxies)))
    if os.path.isfile(cache):
        with io.open(cache, encoding="utf-8") as f:
            return json.load(f)
    log("처음 한 번: 설치된 컴포넌트 목록을 읽는 중이에요 (몇 초 걸려요)…")
    entries, seen = [], set()
    for px in proxies:
        px = unwrap(px)
        try:
            if px.Obsolete:
                continue
            d = px.Desc
            cat, sub, name = str(d.Category), str(d.SubCategory), str(d.Name)
            if cat not in CATEGORIES:
                continue
            key = "%s/%s/%s" % (cat, sub, name)
            if key in EXCLUDE_KEYS or key in seen:
                continue
            if ("%s/%s" % (cat, sub)) in EXCLUDE_SUBCATS and key not in KEEP_IN_EXCLUDED_SUBCATS:
                continue
            obj = unwrap(px.CreateInstance())
            if obj is None:
                continue
            e = {"key": key, "guid": str(px.Guid), "desc": str(d.Description or "")}
            if hasattr(obj, "Params") and hasattr(obj.Params, "Input"):
                e["kind"] = "component"
                e["inputs"] = _params(obj.Params.Input)
                e["outputs"] = _params(obj.Params.Output)
            else:
                e["kind"] = "param"
                e["inputs"], e["outputs"] = [], []
            entries.append(e)
            seen.add(key)
        except Exception:
            continue
    with io.open(cache, "w", encoding="utf-8") as f:
        f.write(json.dumps(entries, ensure_ascii=False))
    log("컴포넌트 %d개를 읽었어요." % len(entries))
    return entries


def model_units():
    try:
        return str(Rhino.RhinoDoc.ActiveDoc.ModelUnitSystem)
    except Exception:
        return "Millimeters"


def call_claude(key, body, progress):
    try:
        return _call_claude(key, body, progress, True)
    except RuntimeError as ex:
        if "fallback" not in str(ex).lower():
            raise
        progress("대체 모델 설정 없이 다시 보내는 중…")
        body = dict(body)
        body.pop("fallbacks", None)
        return _call_claude(key, body, progress, False)


def _call_claude(key, body, progress, use_beta):
    try:
        System.Net.ServicePointManager.SecurityProtocol = (
            System.Net.ServicePointManager.SecurityProtocol | System.Net.SecurityProtocolType.Tls12)
    except Exception:
        pass
    req = unwrap(System.Net.WebRequest.Create(API_URL))
    req.Method = "POST"
    req.ContentType = "application/json"
    req.Timeout = 900000
    try:
        req.ReadWriteTimeout = 900000
    except Exception:
        pass
    req.Headers.Add("x-api-key", key)
    req.Headers.Add("anthropic-version", API_VERSION)
    if use_beta:
        req.Headers.Add("anthropic-beta", API_BETA)
    data = System.Text.Encoding.UTF8.GetBytes(json.dumps(body, ensure_ascii=True))
    req.ContentLength = data.Length
    st = req.GetRequestStream()
    st.Write(data, 0, data.Length)
    st.Close()
    try:
        resp = req.GetResponse()
    except Exception as ex:
        net = getattr(ex, "clsException", ex)
        r = getattr(net, "Response", None) or getattr(ex, "Response", None)
        msg = str(ex)
        if r is not None:
            try:
                msg = System.IO.StreamReader(r.GetResponseStream()).ReadToEnd()
                msg = json.loads(msg).get("error", {}).get("message", msg)
            except Exception:
                pass
        if "authentication" in msg.lower() or "api key" in msg.lower() or "401" in msg:
            msg = "API 키가 맞지 않아요. 키를 다시 확인해 주세요. (" + msg + ")"
        raise RuntimeError(msg)
    reader = System.IO.StreamReader(resp.GetResponseStream(), System.Text.Encoding.UTF8)
    col = StreamCollector()
    last = 0
    while True:
        line = reader.ReadLine()
        if line is None:
            break
        col.feed(str(line))
        if col.chars - last > 400:
            last = col.chars
            progress("받는 중… %d자" % col.chars)
    reader.Close()
    resp.Close()
    return col.result(), col.usage


class Builder(object):
    """그래프 JSON → 캔버스 위 실제 객체."""

    def __init__(self, index):
        self.index = index
        self.objs = {}       # node id → GH 객체
        self.extra = []      # 그룹, 설명 패널
        self.graph = None
        self.origin = None

    # ---- 지우기 / 현재 상태 읽기 ----
    def remove(self, doc):
        for o in list(self.objs.values()) + self.extra:
            try:
                if doc.FindObject(o.InstanceGuid, True) is not None:
                    doc.RemoveObject(o, False)
            except Exception:
                pass
        self.objs, self.extra = {}, []

    def snapshot(self, doc):
        """사용자가 바꾼 슬라이더 값·패널 글·지운 노드를 반영한 현재 그래프."""
        if self.graph is None:
            return None
        g = json.loads(json.dumps(self.graph))
        alive = set()
        for n in g["nodes"]:
            o = self.objs.get(n["id"])
            if o is None or doc.FindObject(o.InstanceGuid, True) is None:
                continue
            alive.add(n["id"])
            tn = o.GetType().Name
            try:
                if tn == "GH_NumberSlider":
                    n["slider_value"] = float(System.Convert.ToDouble(o.Slider.Value))
                elif tn == "GH_Panel":
                    n["text"] = str(o.UserText)
                elif tn == "GH_BooleanToggle":
                    n["toggle"] = bool(o.Value)
            except Exception:
                pass
        g["nodes"] = [n for n in g["nodes"] if n["id"] in alive]
        g["wires"] = [w for w in g["wires"] if w["from_node"] in alive and w["to_node"] in alive]
        return g

    # ---- 짓기 ----
    def _configure(self, o, n):
        tn = o.GetType().Name
        if tn == "GH_NumberSlider":
            mn, mx, v, integer, dec = sanitize_slider(n)
            s = o.Slider
            acc = Grasshopper.GUI.Base.GH_SliderAccuracy
            s.Type = acc.Integer if integer else acc.Float
            s.DecimalPlaces = dec
            s.Minimum = System.Convert.ToDecimal(-1e9)
            s.Maximum = System.Convert.ToDecimal(float(mx))
            s.Minimum = System.Convert.ToDecimal(float(mn))
            s.Value = System.Convert.ToDecimal(float(v))
        elif tn == "GH_Panel":
            o.UserText = n.get("text") or ""
        elif tn == "GH_BooleanToggle":
            o.Value = bool(n.get("toggle"))

    def _out(self, o, ref):
        if hasattr(o, "Params") and hasattr(o.Params, "Output"):
            outs = list(o.Params.Output)
            i = match_param([(str(p.Name), str(p.NickName)) for p in outs], ref)
            return unwrap(outs[i]) if i is not None else None
        return o

    def _in(self, o, ref):
        if hasattr(o, "Params") and hasattr(o.Params, "Input"):
            ins = list(o.Params.Input)
            i = match_param([(str(p.Name), str(p.NickName)) for p in ins], ref)
            return unwrap(ins[i]) if i is not None else None
        return o

    def build(self, doc, graph, origin):
        issues = []
        self.graph, self.origin = graph, origin
        added = []
        proto_ids = set()
        for bl in graph.get("blocks", []):
            proto_ids.update(bl.get("parts", []))
        # 화면이 점·선으로 어지럽지 않게: 최종 결과(bake)와 미리보기용 노드만 보이고 중간 단계는 숨긴다
        shown = set(bake_targets(graph)) | set(n["id"] for n in graph["nodes"] if n.get("preview"))
        hide_mid = bool(shown)
        for n in graph["nodes"]:
            e = self.index.resolve(n.get("component"))
            if e is None:
                issues.append("node %s: unknown component '%s' (skipped)" % (n["id"], n.get("component")))
                continue
            o = unwrap(Grasshopper.Instances.ComponentServer.EmitObject(System.Guid(e["guid"])))
            if o is None:
                issues.append("node %s: could not create '%s'" % (n["id"], e["key"]))
                continue
            o.CreateAttributes()
            if n.get("nickname"):
                o.NickName = n["nickname"]
            try:
                self._configure(o, n)
            except Exception as ex:
                issues.append("node %s: setting values failed (%s)" % (n["id"], ex))
            if n["id"] in proto_ids or (hide_mid and n["id"] not in shown and
                                        not (n.get("component") or "").startswith(PARAM_PREFIX)):
                try:
                    o.Hidden = True   # 블록 원형은 원점에 있으므로 미리보기에서 숨긴다
                except Exception:
                    pass
            doc.AddObject(o, False)
            self.objs[n["id"]] = o
            added.append(o)

        for w in graph["wires"]:
            a, b = self.objs.get(w["from_node"]), self.objs.get(w["to_node"])
            if a is None or b is None:
                continue
            src, dst = self._out(a, w.get("from_output")), self._in(b, w.get("to_input"))
            if src is None:
                issues.append("node %s: no output '%s'" % (w["from_node"], w.get("from_output")))
                continue
            if dst is None:
                issues.append("node %s: no input '%s'" % (w["to_node"], w.get("to_input")))
                continue
            dst.AddSource(src)
            m = w.get("mapping", "none")
            if m == "graft":
                dst.DataMapping = GK.GH_DataMapping.Graft
            elif m == "flatten":
                dst.DataMapping = GK.GH_DataMapping.Flatten

        # 크기 재고 배치
        sizes, offs = {}, {}
        for nid, o in self.objs.items():
            at = o.Attributes
            at.Pivot = SD.PointF(0, 0)
            at.ExpireLayout()
            at.PerformLayout()
            b = at.Bounds
            sizes[nid] = (float(b.Width), float(b.Height))
            offs[nid] = (float(b.X), float(b.Y))
        ox, oy = origin
        pos = layout_positions(graph, sizes, (ox, oy + 260))
        for nid, (x, y) in pos.items():
            at = self.objs[nid].Attributes
            at.Pivot = SD.PointF(float(x - offs[nid][0]), float(y - offs[nid][1]))
            at.ExpireLayout()
            at.PerformLayout()

        # 그룹
        palette = [(70, 130, 210), (90, 150, 220), (60, 110, 190), (110, 165, 230), (80, 120, 170)]
        for gi, g in enumerate(graph.get("groups", [])):
            ids = [n["id"] for n in graph["nodes"] if n.get("group") == g["id"] and n["id"] in self.objs]
            if not ids:
                continue
            grp = Grasshopper.Kernel.Special.GH_Group()
            grp.CreateAttributes()
            grp.NickName = g.get("label") or g["id"]
            r, gg, bb = palette[gi % len(palette)]
            grp.Colour = SD.Color.FromArgb(55, r, gg, bb)
            for nid in ids:
                grp.AddObject(self.objs[nid].InstanceGuid)
            doc.AddObject(grp, False)
            grp.ExpireCaches()
            self.extra.append(grp)

        # 설명 패널
        lines = [u"■ " + graph.get("title", ""), "", graph.get("summary", ""), ""]
        for g in graph.get("groups", []):
            lines.append(u"%s — %s" % (g.get("label", ""), g.get("note", "")))
        lines += ["", u"쓰는 법: " + graph.get("notes", ""), "", u"(GH AI 빌더 v%s)" % VERSION]
        try:
            p = Grasshopper.Kernel.Special.GH_Panel()
            p.CreateAttributes()
            p.NickName = u"설명"
            p.UserText = "\n".join(lines)
            p.Attributes.Bounds = SD.RectangleF(float(ox), float(oy), 560.0, 230.0)
            p.Attributes.Pivot = SD.PointF(float(ox), float(oy))
            doc.AddObject(p, False)
            self.extra.append(p)
        except Exception:
            pass

        # 정의 정보를 캔버스에 같이 저장 → .gh를 다시 열어도 고치기·Bake·재료가 이어진다
        try:
            data = {"v": 1, "origin": [ox, oy], "graph": graph,
                    "map": dict((k, str(o.InstanceGuid)) for k, o in self.objs.items()),
                    "extra": [str(o.InstanceGuid) for o in self.extra],
                    "legacy_tags": list(getattr(self, "legacy_tags", []) or [])}
            dp = Grasshopper.Kernel.Special.GH_Panel()
            dp.CreateAttributes()
            dp.NickName = DATA_PANEL
            dp.UserText = json.dumps(data, ensure_ascii=False)
            dp.Attributes.Bounds = SD.RectangleF(float(ox) + 580.0, float(oy), 200.0, 40.0)
            dp.Attributes.Pivot = SD.PointF(float(ox) + 580.0, float(oy))
            doc.AddObject(dp, False)
            self.extra.append(dp)
        except Exception:
            pass
        try:
            doc.UndoUtil.RecordAddObjectEvent("GH AI", added + self.extra)
        except Exception:
            pass
        return issues

    def bake(self, doc):
        """이 창에서 만든 정의의 마지막 결과를 Rhino 객체로 넣는다."""
        root = "GH_AI::" + safe_layer_name(self.graph.get("title", ""))
        nicks = dict((n["id"], n.get("nickname") or n["id"]) for n in self.graph["nodes"])
        mats = dict((n["id"], n.get("material", "")) for n in self.graph["nodes"])
        targets = []
        for nid in bake_targets(self.graph):
            o = self.objs.get(nid)
            if o is not None and doc.FindObject(o.InstanceGuid, True) is not None:
                targets.append((o, nicks[nid], mats.get(nid, "")))
        tag = self.tag()
        self.removed = delete_baked(tag)
        for t in self.old_tags():
            self.removed += delete_baked(t)
        n, layer = bake_objects(targets, root, tag)
        self.block_report = []
        if self.graph.get("blocks"):
            ni, self.block_report = bake_blocks(self.graph, self.objs, root, tag)
            n += ni
        return n, layer

    def tag(self):
        """이 정의의 Bake 결과를 구별하는 표 = 제목. 같은 제목으로 다시 Bake하면 예전 것을 바꾼다."""
        return "title:" + (self.graph.get("title") or "GH")

    def old_tags(self):
        """예전 판(v0.7~0.8)이 쓰던 표(DATA 패널 id)와, 바꿔 지은 예전 정의의 표."""
        tags = list(getattr(self, "legacy_tags", []) or [])
        for o in self.extra:
            try:
                if str(o.NickName) == DATA_PANEL:
                    tags.append(str(o.InstanceGuid))
            except Exception:
                pass
        return tags

    def run_and_collect(self, doc):
        doc.NewSolution(False)
        errors, warnings = [], []
        lv = GK.GH_RuntimeMessageLevel
        for nid, o in self.objs.items():
            if not hasattr(o, "RuntimeMessages"):
                continue
            for m in o.RuntimeMessages(lv.Error):
                errors.append("node %s (%s): ERROR %s" % (nid, o.Name, m))
            for m in o.RuntimeMessages(lv.Warning):
                warnings.append("node %s (%s): WARNING %s" % (nid, o.Name, m))
        return errors, warnings


def _first_output(o):
    if hasattr(o, "Params") and hasattr(o.Params, "Output"):
        outs = list(o.Params.Output)
        return unwrap(outs[0]) if outs else None
    return o


def apply_material(rdoc, layer_index, mkey):
    """레이어에 재료 색과 렌더 재질을 붙인다."""
    name, rgb, transp, refl = MATERIALS[mkey]
    lay = rdoc.Layers[layer_index]
    lay.Color = SD.Color.FromArgb(rgb[0], rgb[1], rgb[2])
    try:
        rm = None
        for r in rdoc.RenderMaterials:
            if str(r.Name) == u"GH_AI " + name:
                rm = r
                break
        if rm is None:
            m = Rhino.DocObjects.Material()
            m.Name = u"GH_AI " + name
            m.DiffuseColor = lay.Color
            m.Transparency = transp
            m.Reflectivity = refl
            rm = Rhino.Render.RenderMaterial.CreateBasicMaterial(m, rdoc)
            rdoc.RenderMaterials.Add(rm)
        lay.RenderMaterial = rm
    except Exception:
        pass
    try:
        rdoc.Layers.Modify(lay, layer_index, True)
    except Exception:
        pass


def goo_to_geometry(goo):
    """GH 데이터 하나 → Rhino GeometryBase (못 바꾸면 None)."""
    G = Rhino.Geometry
    try:
        v = goo.ScriptVariable()
    except Exception:
        return None
    if isinstance(v, G.Box):
        return v.ToBrep()
    if isinstance(v, G.Point3d):
        return G.Point(v)
    if isinstance(v, G.Line):
        return G.LineCurve(v)
    if isinstance(v, G.Rectangle3d):
        return v.ToNurbsCurve()
    if isinstance(v, G.Circle):
        return G.ArcCurve(v)
    if isinstance(v, G.Arc):
        return G.ArcCurve(v)
    if isinstance(v, G.GeometryBase):
        return v
    return None


def goo_to_plane(goo):
    G = Rhino.Geometry
    try:
        v = goo.ScriptVariable()
    except Exception:
        return None
    if isinstance(v, G.Plane):
        return v
    if isinstance(v, G.Point3d):
        return G.Plane(v, G.Vector3d.ZAxis)
    if isinstance(v, G.Point):
        return G.Plane(v.Location, G.Vector3d.ZAxis)
    return None


TAG_KEY = "GH_AI"


def delete_baked(tag):
    """같은 정의로 예전에 Bake한 객체를 지운다. → 지운 개수"""
    if not tag:
        return 0
    rdoc = Rhino.RhinoDoc.ActiveDoc
    ids = []
    for ro in rdoc.Objects:
        try:
            if ro.Attributes.GetUserString(TAG_KEY) == tag:
                ids.append(ro.Id)
        except Exception:
            pass
    for i in ids:
        rdoc.Objects.Delete(i, True)
    return len(ids)


def bake_blocks(graph, objs, root, tag=""):
    """blocks 항목마다: 원형 부재들 → 블록 정의 1개, 위치 평면마다 블록 인스턴스."""
    rdoc = Rhino.RhinoDoc.ActiveDoc
    G = Rhino.Geometry
    from System.Collections.Generic import List as NetList
    mats = dict((n["id"], n.get("material", "")) for n in graph["nodes"])
    nicks = dict((n["id"], n.get("nickname") or n["id"]) for n in graph["nodes"])
    total_inst, report = 0, []
    for b in graph.get("blocks", []):
        geoms = NetList[G.GeometryBase]()
        attrs = NetList[Rhino.DocObjects.ObjectAttributes]()
        for pid in b.get("parts", []):
            o = objs.get(pid)
            param = _first_output(o) if o is not None else None
            if param is None:
                continue
            a = Rhino.DocObjects.ObjectAttributes()
            mkey = material_for(mats.get(pid))
            if mkey:
                a.LayerIndex = ensure_layer(rdoc, root + "::" + MATERIALS[mkey][0] + "::" + safe_layer_name(nicks[pid]))
                apply_material(rdoc, a.LayerIndex, mkey)
            else:
                a.LayerIndex = ensure_layer(rdoc, root + "::" + safe_layer_name(nicks[pid]))
            for goo in param.VolatileData.AllData(True):
                g = goo_to_geometry(unwrap(goo))
                if g is not None:
                    geoms.Add(g)
                    attrs.Add(a)
        at = objs.get(b.get("at"))
        pparam = _first_output(at) if at is not None else None
        if geoms.Count == 0 or pparam is None:
            report.append(u"%s: 원형이나 위치가 비어 있어 건너뜀" % b.get("name"))
            continue
        name = safe_layer_name(graph.get("title", ""))[:30] + " - " + safe_layer_name(b.get("name"))
        idef = rdoc.InstanceDefinitions.Find(name)
        if idef is None:
            idx = rdoc.InstanceDefinitions.Add(name, "GH AI", G.Point3d.Origin, geoms, attrs)
        else:
            idx = idef.Index
            rdoc.InstanceDefinitions.ModifyGeometry(idx, geoms, attrs)
        ia = Rhino.DocObjects.ObjectAttributes()
        ia.LayerIndex = ensure_layer(rdoc, root + u"::블록::" + safe_layer_name(b.get("name")))
        if tag:
            ia.SetUserString(TAG_KEY, tag)
        n = 0
        for goo in pparam.VolatileData.AllData(True):
            pl = goo_to_plane(unwrap(goo))
            if pl is None:
                continue
            xf = G.Transform.PlaneToPlane(G.Plane.WorldXY, pl)
            if rdoc.Objects.AddInstanceObject(idx, xf, ia) != System.Guid.Empty:
                n += 1
        total_inst += n
        report.append(u"%s: 블록 1개 정의, %d개 배치" % (b.get("name"), n))
    return total_inst, report


def bake_objects(targets, root, tag=""):
    """targets: [(GH 객체, 이름[, 재료])] → 첫 번째 출력의 형상을 root::(재료::)이름 레이어로 넣는다."""
    rdoc = Rhino.RhinoDoc.ActiveDoc
    G = Rhino.Geometry
    total = 0
    for t in targets:
        o, label = t[0], t[1]
        mkey = material_for(t[2]) if len(t) > 2 else None
        param = _first_output(o)
        if param is None:
            continue
        attr = Rhino.DocObjects.ObjectAttributes()
        if mkey:
            path = root + "::" + MATERIALS[mkey][0] + "::" + safe_layer_name(label)
            attr.LayerIndex = ensure_layer(rdoc, path)
            apply_material(rdoc, attr.LayerIndex, mkey)
        else:
            attr.LayerIndex = ensure_layer(rdoc, root + "::" + safe_layer_name(label))
        if tag:
            attr.SetUserString(TAG_KEY, tag)
        for goo in param.VolatileData.AllData(True):
            g = goo_to_geometry(unwrap(goo))
            if g is not None and rdoc.Objects.Add(g, attr) != System.Guid.Empty:
                total += 1
    rdoc.Views.Redraw()
    return total, root


def canvas_bake_targets(doc):
    """창이 기억하는 정의가 없을 때: 캔버스에서 선택한 컴포넌트, 없으면
    출력선이 나가지 않는(= 마지막) 컴포넌트 중 미리보기가 켜진 것."""
    sel = [unwrap(o) for o in doc.SelectedObjects()]
    sel = [o for o in sel if hasattr(o, "Params") or hasattr(o, "VolatileData")]
    if sel:
        return [(o, str(o.NickName)) for o in sel]
    out = []
    for o in doc.Objects:
        o = unwrap(o)
        if not (hasattr(o, "Params") and hasattr(o.Params, "Output")):
            continue
        if getattr(o, "Hidden", False) or getattr(o, "Locked", False):
            continue
        outs = list(o.Params.Output)
        ins = list(o.Params.Input)
        if not outs or not ins:
            continue
        if any(unwrap(p).Recipients.Count > 0 for p in outs):
            continue
        if not any(unwrap(p).SourceCount > 0 for p in ins):
            continue
        out.append((o, str(o.NickName)))
    return out


def ensure_layer(rdoc, path):
    """'A::B::C' 레이어를 (없으면 만들어) 번호를 돌려준다."""
    idx = rdoc.Layers.FindByFullPath(path, -1)
    if idx >= 0:
        return idx
    parent_id = System.Guid.Empty
    cur = ""
    for part in path.split("::"):
        cur = part if not cur else cur + "::" + part
        idx = rdoc.Layers.FindByFullPath(cur, -1)
        if idx < 0:
            lay = Rhino.DocObjects.Layer()
            lay.Name = part
            if parent_id != System.Guid.Empty:
                lay.ParentLayerId = parent_id
            idx = rdoc.Layers.Add(lay)
        parent_id = rdoc.Layers[idx].Id
    return idx


DATA_PANEL = "GH_AI_DATA (지우지 마세요)"


def restore_all_builders(doc, index):
    """캔버스에 있는 GH_AI 정의 전부 (GH_AI_DATA 패널마다 하나)."""
    out = []
    for o in doc.Objects:
        o = unwrap(o)
        if o.GetType().Name == "GH_Panel" and str(o.NickName) == DATA_PANEL:
            try:
                d = json.loads(str(o.UserText))
            except Exception:
                continue
            b = Builder(index)
            b.graph = normalize_graph(d["graph"])
            b.origin = tuple(d.get("origin", (60.0, 60.0)))
            for nid, g in d.get("map", {}).items():
                x = doc.FindObject(System.Guid(g), True)
                if x is not None:
                    b.objs[nid] = unwrap(x)
            for g in d.get("extra", []):
                x = doc.FindObject(System.Guid(g), True)
                if x is not None:
                    b.extra.append(unwrap(x))
            b.extra.append(o)
            b.legacy_tags = d.get("legacy_tags", [])
            if b.objs:
                out.append(b)
    return out


def restore_builder(doc, index):
    """캔버스에 저장된 GH_AI_DATA 패널에서 정의를 되살린다. 선택한 객체가 속한 정의를 우선."""
    sel = set(str(unwrap(o).InstanceGuid) for o in doc.SelectedObjects())
    found = []
    for o in doc.Objects:
        o = unwrap(o)
        if o.GetType().Name == "GH_Panel" and str(o.NickName) == DATA_PANEL:
            try:
                found.append((o, json.loads(str(o.UserText))))
            except Exception:
                pass
    if not found:
        return None
    pick = found[-1]
    for o, d in found:
        if sel & set(d.get("map", {}).values()):
            pick = (o, d)
    panel, d = pick
    b = Builder(index)
    b.graph = normalize_graph(d["graph"])
    b.origin = tuple(d.get("origin", (60.0, 60.0)))
    for nid, g in d.get("map", {}).items():
        o = doc.FindObject(System.Guid(g), True)
        if o is not None:
            b.objs[nid] = unwrap(o)
    for g in d.get("extra", []):
        o = doc.FindObject(System.Guid(g), True)
        if o is not None:
            b.extra.append(unwrap(o))
    b.extra.append(panel)
    b.legacy_tags = d.get("legacy_tags", [])
    return b if b.objs else None


def free_origin(doc):
    bottom, left, any_obj = None, None, False
    for o in doc.Objects:
        try:
            b = o.Attributes.Bounds
        except Exception:
            continue
        any_obj = True
        bottom = b.Bottom if bottom is None else max(bottom, b.Bottom)
        left = b.Left if left is None else min(left, b.Left)
    if not any_obj:
        return (60.0, 60.0)
    return (float(left), float(bottom) + 150.0)


# =====================================================================
# 창 (Eto)
# =====================================================================

def black_button(text):
    b = forms.Button()
    b.Text = text
    try:
        b.BackgroundColor = drawing.Colors.Black
        b.TextColor = drawing.Colors.White
    except Exception:
        pass
    return b


class App(object):
    def __init__(self):
        self.version = VERSION
        self.busy = False
        self.builder = None
        self.catalog = None
        self.index = None
        self.cat_txt = None
        self.cost_tokens = 0
        self._make_form()

    # ---- UI ----
    def _make_form(self):
        f = forms.Form()
        f.Title = u"GH AI 빌더 v%s — 말로 그래스호퍼 정의 만들기" % VERSION
        f.Resizable = True
        f.ClientSize = drawing.Size(560, 700)
        f.BackgroundColor = drawing.Colors.White

        self.preset = forms.DropDown()
        for name, _ in PRESETS:
            self.preset.Items.Add(name)
        self.preset.SelectedIndex = 0
        self.preset.SelectedIndexChanged += self.on_preset

        self.req = forms.TextArea()
        self.req.Size = drawing.Size(-1, 140)
        self.req.Wrap = True

        self.btn_new = black_button(u"새로 만들기")
        self.btn_new.Click += self.on_new
        self.btn_edit = black_button(u"지금 정의 고치기")
        self.btn_edit.Click += self.on_edit
        self.btn_bake = black_button(u"결과 Bake (Rhino로 넣기)")
        self.btn_bake.Click += self.on_bake
        self.btn_cat = black_button(u"컴포넌트 목록 저장")
        self.btn_cat.Click += self.on_export_catalog
        self.btn_copy = black_button(u"지금 정의 JSON 복사")
        self.btn_copy.Click += self.on_copy_json
        self.autofix = forms.CheckBox()
        self.autofix.Text = u"오류가 나면 자동으로 고치기 (최대 %d번)" % MAX_FIX_ROUNDS
        self.autofix.Checked = True
        self.replace_old = forms.CheckBox()
        self.replace_old.Text = u"새로 만들 때 캔버스의 예전 GH AI 정의는 지우고 그 자리에 만들기"
        self.replace_old.Checked = True

        self.status = forms.Label()
        self.status.Text = u"준비됨"
        self.status.TextColor = drawing.Color.FromArgb(30, 90, 200)

        self.logbox = forms.TextArea()
        self.logbox.ReadOnly = True
        self.logbox.Wrap = True
        self.logbox.Size = drawing.Size(-1, 230)

        self.key = forms.PasswordBox()
        self.key.Text = load_key()
        self.btn_key = black_button(u"키 저장")
        self.btn_key.Click += self.on_key

        lay = forms.DynamicLayout()
        lay.Padding = drawing.Padding(12)
        lay.Spacing = drawing.Size(6, 8)
        lay.AddRow(self._label(u"예시 고르기 (또는 직접 적기)"))
        lay.AddRow(self.preset)
        lay.AddRow(self._label(u"만들고 싶은 것 — 또는 Claude 스레드에서 받은 JSON을 그대로 붙여 넣기 (무료)"))
        lay.AddRow(self.req)
        lay.AddRow(self.btn_new, self.btn_edit)
        lay.AddRow(self.btn_bake)
        lay.AddRow(self.btn_copy, self.btn_cat)
        lay.AddRow(self.autofix)
        lay.AddRow(self.replace_old)
        lay.AddRow(self.status)
        lay.AddRow(self.logbox)
        lay.AddRow(self._label(u"Claude API 키 (한 번만 저장하면 돼요)"))
        lay.AddRow(self.key, self.btn_key)
        lay.Add(None)
        f.Content = lay
        try:
            f.Owner = Rhino.UI.RhinoEtoApp.MainWindow
        except Exception:
            pass
        f.Closed += self.on_closed
        self.form = f

    def _label(self, t):
        l = forms.Label()
        l.Text = t
        return l

    def show(self):
        self.form.Show()

    # ---- 로그 ----
    def log(self, msg):
        def f():
            self.logbox.Append(msg + "\n", True)
        self.ui(f)

    def set_status(self, msg):
        def f():
            self.status.Text = msg
        self.ui(f)

    def ui(self, fn):
        forms.Application.Instance.AsyncInvoke(System.Action(fn))

    # ---- 이벤트 ----
    def on_closed(self, s, e):
        sc.sticky.pop("gh_ai_app", None)

    def on_preset(self, s, e):
        i = self.preset.SelectedIndex
        if i > 0:
            self.req.Text = PRESETS[i][1]

    def on_key(self, s, e):
        save_key(self.key.Text or "")
        self.log(u"API 키를 저장했어요. (내 PC의 %APPDATA%\\GH_AI\\api_key.txt — 다른 사람과 공유하지 마세요)")

    def on_export_catalog(self, s, e):
        try:
            ensure_gh_doc()
            if self.catalog is None:
                self.catalog = build_catalog(self.log)
                self.index = CatalogIndex(self.catalog)
                self.cat_txt = catalog_text(self.catalog)
            desk = str(System.Environment.GetFolderPath(System.Environment.SpecialFolder.Desktop))
            path = os.path.join(desk, u"GH_컴포넌트목록.txt")
            with io.open(path, "w", encoding="utf-8") as f:
                f.write(self.cat_txt)
            self.log(u"바탕화면에 저장했어요: %s (Claude 스레드에 올려 주면 정확한 이름으로 만들어요)" % path)
        except Exception as ex:
            self.log(u"목록 저장 오류: %s" % ex)

    def current_builder(self, doc):
        """창이 기억하는 정의가 캔버스에 살아 있으면 그것, 아니면 캔버스에 저장된 것."""
        if self.catalog is None:
            self.catalog = build_catalog(self.log)
            self.index = CatalogIndex(self.catalog)
            self.cat_txt = catalog_text(self.catalog)
        b = self.builder
        if b is not None and b.graph is not None and any(
                doc.FindObject(o.InstanceGuid, True) is not None for o in b.objs.values()):
            return b
        b = restore_builder(doc, self.index)
        if b is not None:
            self.builder = b
            self.log(u"캔버스에 저장된 정의를 불러왔어요: %s" % b.graph.get("title", ""))
        return b

    def on_bake(self, s, e):
        try:
            canvas, doc = ensure_gh_doc()
            if self.catalog is None:
                self.catalog = build_catalog(self.log)
                self.index = CatalogIndex(self.catalog)
                self.cat_txt = catalog_text(self.catalog)
            builders = [] if list(doc.SelectedObjects()) else restore_all_builders(doc, self.index)
            if builders:
                # 캔버스에 있는 GH_AI 정의 전부. 같은 정의를 다시 Bake하면 예전 결과를 지우고 바꾼다.
                self.log(u"캔버스의 정의 %d개를 Bake해요." % len(builders))
                n = 0
                for b in builders:
                    nb, layer = b.bake(doc)
                    n += nb
                    msg = u"  ✓ %s: %d개" % (b.graph.get("title", ""), nb)
                    if getattr(b, "removed", 0):
                        msg += u" (예전 Bake %d개는 지우고 바꿨어요)" % b.removed
                    self.log(msg)
                    for r in getattr(b, "block_report", []):
                        self.log(u"     블록 " + r)
                layer = "GH_AI"
            else:
                targets = canvas_bake_targets(doc)
                if not targets:
                    self.log(u"Bake할 컴포넌트를 찾지 못했어요. 캔버스에서 넣고 싶은 컴포넌트를 클릭해 선택한 뒤 다시 눌러 주세요.")
                    return
                name = os.path.splitext(str(doc.DisplayName or "GH"))[0].replace("*", "")
                self.log(u"캔버스에서 고른 컴포넌트: " + ", ".join(t[1] for t in targets))
                n, layer = bake_objects(targets, "GH_AI::" + safe_layer_name(name))
            if n == 0:
                self.log(u"Bake할 결과가 없어요. 마지막 컴포넌트에 오류가 없는지 확인해 주세요.")
            else:
                self.log(u"✓ %d개를 Rhino에 넣었어요. 레이어: %s (슬라이더를 바꿔도 이건 그대로예요)" % (n, layer))
        except Exception as ex:
            self.log(u"Bake 오류: %s" % ex)
            self.log(traceback.format_exc()[-600:])

    def on_copy_json(self, s, e):
        try:
            canvas, doc = ensure_gh_doc()
            b = self.current_builder(doc)
            g = b.snapshot(doc) if b is not None else None
            if g is None:
                self.log(u"복사할 정의가 없어요.")
                return
            cb = forms.Clipboard()
            cb.Text = json.dumps(g, ensure_ascii=False)
            self.log(u"지금 정의(슬라이더 값 포함)를 클립보드에 복사했어요. 스레드에 붙여 넣고 고칠 점을 적어 주세요.")
        except Exception as ex:
            self.log(u"복사 오류: %s" % ex)

    def on_new(self, s, e):
        self.start(edit=False)

    def on_edit(self, s, e):
        self.start(edit=True)

    # ---- 흐름 ----
    def start(self, edit):
        if self.busy:
            return
        try:
            pasted = parse_pasted(self.req.Text)
        except Exception as ex:
            self.log(u"붙여 넣은 JSON을 읽을 수 없어요: %s" % ex)
            return
        if pasted is not None:
            try:
                ensure_gh_doc()
                if self.catalog is None:
                    self.catalog = build_catalog(self.log)
                    self.index = CatalogIndex(self.catalog)
                    self.cat_txt = catalog_text(self.catalog)
            except Exception as ex:
                self.log(u"준비 중 오류: %s" % ex)
                return
            self.log(u"\n── 붙여 넣은 정의로 %s (API 사용 안 함): %s" % (
                u"고치기" if edit else u"새로 만들기", pasted.get("title", "")))
            self.free_mode = True
            self.busy = True
            if edit:
                self.current_builder(ensure_gh_doc()[1])
            self.place("", "", pasted, edit and self.builder is not None, MAX_FIX_ROUNDS)
            return
        self.free_mode = False
        key = (self.key.Text or "").strip() or load_key()
        if not key:
            self.log(u"먼저 아래 칸에 Claude API 키를 넣고 [키 저장]을 눌러 주세요.")
            return
        request = (self.req.Text or "").strip()
        if not request:
            self.log(u"만들고 싶은 것을 적어 주세요.")
            return
        try:
            canvas, doc = ensure_gh_doc()
            if self.catalog is None:
                self.catalog = build_catalog(self.log)
                self.index = CatalogIndex(self.catalog)
                self.cat_txt = catalog_text(self.catalog)
            current = None
            if edit:
                self.current_builder(doc)
                if self.builder is None or self.builder.graph is None:
                    self.log(u"고칠 정의가 없어요. 먼저 [새로 만들기]를 눌러 주세요.")
                    return
                current = self.builder.snapshot(doc)
        except Exception as ex:
            self.log(u"준비 중 오류: %s" % ex)
            return
        self.busy = True
        self.btn_new.Enabled = self.btn_edit.Enabled = False
        self.log(u"\n── %s: %s" % (u"고치기" if edit else u"새로 만들기", request[:80]))
        user_msg = build_user_message(request, model_units(), current)
        t = threading.Thread(target=self.worker, args=(key, request, user_msg, edit, 0))
        t.daemon = True
        t.start()

    def worker(self, key, request, user_msg, edit, round_no):
        try:
            self.set_status(u"Claude가 알고리즘을 설계하는 중… (보통 20초~2분)")
            body = build_request_body(self.cat_txt, user_msg)
            graph, usage = call_claude(key, body, self.set_status)
            graph = normalize_graph(graph)
            self.log(u"설계 완료: %s (노드 %d개, 선 %d개)" % (
                graph.get("title", ""), len(graph.get("nodes", [])), len(graph.get("wires", []))))
            if usage:
                self.log(u"  토큰: 입력 %s / 캐시 읽기 %s / 출력 %s" % (
                    usage.get("input_tokens"), usage.get("cache_read_input_tokens"), usage.get("output_tokens")))
            self.ui(lambda: self.place(key, request, graph, edit, round_no))
        except Exception as ex:
            self.log(u"오류: %s" % ex)
            self.log(traceback.format_exc()[-600:])
            self.ui(self.done)

    def place(self, key, request, graph, edit, round_no):
        try:
            canvas, doc = ensure_gh_doc()
            pre = validate_graph(graph, self.index)
            if edit and self.builder is not None:
                origin = self.builder.origin
                self.builder.remove(doc)
                self.builder.index = self.index
            else:
                old = restore_all_builders(doc, self.index) if self.replace_old.Checked else []
                legacy = []
                if old:
                    origin = min((b.origin for b in old), key=lambda o: (o[1], o[0]))
                    for b in old:
                        legacy += b.old_tags()
                        b.remove(doc)
                    self.log(u"  예전 GH AI 정의 %d개를 지우고 그 자리에 새로 만들어요." % len(old))
                else:
                    origin = free_origin(doc)
                self.builder = Builder(self.index)
                self.builder.legacy_tags = legacy
            issues = self.builder.build(doc, graph, origin)
            errors, warnings = self.builder.run_and_collect(doc)
            canvas.Refresh()
            problems = list(dict.fromkeys(pre + issues + errors +
                                          [w for w in warnings if "collect" in w.lower() or "failed" in w.lower()]))
            if warnings:
                self.log(u"  경고 %d개" % len(warnings))
                for w in warnings[:8]:
                    self.log(u"   · " + w)
            if not problems:
                self.log(u"✓ 캔버스에 만들었어요. 슬라이더를 움직여 보세요.")
                self.done()
                return
            self.log(u"  문제 %d개:" % len(problems))
            for p in problems[:12]:
                self.log(u"   · " + p)
            if self.autofix.Checked and round_no < MAX_FIX_ROUNDS:
                self.log(u"  → 자동으로 고치는 중 (%d/%d)" % (round_no + 1, MAX_FIX_ROUNDS))
                current = self.builder.snapshot(doc) or graph
                msg = build_user_message(request, model_units(), current, problems)
                t = threading.Thread(target=self.worker, args=(key, request, msg, True, round_no + 1))
                t.daemon = True
                t.start()
                return
            if getattr(self, "free_mode", False):
                self.log(u"→ 이 기록을 그대로 복사해서 Claude 스레드에 보내 주세요. 고친 JSON을 드릴게요.")
            else:
                self.log(u"남은 문제가 있어요. [지금 정의 고치기]에 고칠 점을 적어 다시 시도해 보세요.")
            self.done()
        except Exception as ex:
            self.log(u"캔버스에 만드는 중 오류: %s" % ex)
            self.log(traceback.format_exc()[-800:])
            self.done()

    def done(self):
        self.busy = False
        self.btn_new.Enabled = self.btn_edit.Enabled = True
        self.status.Text = u"준비됨"


def main():
    old = sc.sticky.get("gh_ai_app")
    if old is not None:
        try:
            if getattr(old, "version", None) == VERSION:
                old.form.BringToFront()
                return
            old.form.Close()   # 예전 버전 창은 닫고 새로 연다
        except Exception:
            pass
    app = App()
    sc.sticky["gh_ai_app"] = app
    app.show()


if __name__ == "__main__" and IN_RHINO:
    main()
