# -*- coding: utf-8 -*-
"""그래스호퍼 흉내 검사기 (Rhino 없이 예시 JSON을 실제로 계산해 보고 그림으로 그린다).

- 데이터 트리(경로·가지 짝짓기·가장 긴 목록·Graft/Flatten)를 그래스호퍼 규칙에 가깝게 따른다.
- 형상은 점·벡터·평면·폴리선·면(다각형 면 모음)으로 근사한다. 곡선은 꺾은선으로 근사.
- 입력 기본값은 실제 그래스호퍼 기본값을 따르려 했다 (예: Evaluate Length의 Normalized = True).
- 결과: 노드별 출력 트리, 경고/오류, Bake 대상과 블록 배치 → render()로 PNG.
사용: python3 ghsim.py ../examples/07_....json out.png
"""
import json, math, sys, os, re
from collections import OrderedDict
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import GH_AI_builder as B  # noqa


# ------------------------------------------------------------------ 형상
class Vec(object):
    __slots__ = ("v",)
    def __init__(s, v): s.v = np.asarray(v, float)
    def xf(s, M): return Vec(M[:3, :3] @ s.v)
    def __repr__(s): return "Vec(%.1f,%.1f,%.1f)" % tuple(s.v)


class Plane(object):
    __slots__ = ("o", "x", "y", "z")
    def __init__(s, o, x, y):
        s.o = np.asarray(o, float)
        x = np.asarray(x, float); x = x / np.linalg.norm(x)
        y = np.asarray(y, float); y = y - x * (x @ y); y = y / np.linalg.norm(y)
        s.x, s.y, s.z = x, y, np.cross(x, y)
    @staticmethod
    def world(o=(0, 0, 0)): return Plane(o, (1, 0, 0), (0, 1, 0))
    def to_world(s, p): p = np.asarray(p, float); return s.o + p[..., 0:1] * s.x + p[..., 1:2] * s.y + p[..., 2:3] * s.z
    def matrix(s):  # 평면 좌표 → 월드
        M = np.eye(4); M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = s.x, s.y, s.z, s.o; return M
    def xf(s, M):
        o = M[:3, :3] @ s.o + M[:3, 3]
        return Plane(o, M[:3, :3] @ s.x, M[:3, :3] @ s.y)


class Curve(object):
    """꺾은선. 매개변수 영역 = [0, 선분 수] (Rhino 폴리선과 같음)."""
    __slots__ = ("p", "closed")
    def __init__(s, pts, closed=False):
        p = np.asarray(pts, float)
        if closed and len(p) > 1 and np.allclose(p[0], p[-1]):
            p = p[:-1]
        s.p, s.closed = p, closed
    def verts(s): return np.vstack([s.p, s.p[:1]]) if s.closed else s.p
    def segs(s):
        v = s.verts(); return [Curve(v[i:i + 2]) for i in range(len(v) - 1)]
    def lengths(s):
        v = s.verts(); return np.linalg.norm(np.diff(v, axis=0), axis=1)
    def length(s): return float(s.lengths().sum())
    def at_param(s, t):
        v = s.verts(); n = len(v) - 1
        t = min(max(t, 0.0), n)
        i = min(int(math.floor(t)), n - 1); f = t - i
        d = v[i + 1] - v[i]; L = np.linalg.norm(d)
        return v[i] + f * d, (d / L if L > 0 else np.zeros(3))
    def param_at_length(s, L):
        ls = s.lengths(); acc = 0.0
        for i, l in enumerate(ls):
            if L <= acc + l + 1e-9:
                return i + ((L - acc) / l if l > 0 else 0.0)
            acc += l
        return float(len(ls))
    def xf(s, M): return Curve((M[:3, :3] @ s.p.T).T + M[:3, 3], s.closed)
    def planar_plane(s):
        c = s.p.mean(0); u, sv, vt = np.linalg.svd(s.p - c); n = vt[2]
        x = s.p[0] - c
        if np.linalg.norm(x) < 1e-9: x = vt[0]
        return Plane(c, x - n * (x @ n), np.cross(n, x - n * (x @ n)))


class Mesh(object):
    """면 모음: faces = [ (k×3 꼭짓점 배열) ... ]. solid/surface 모두 이걸로."""
    __slots__ = ("faces", "kind")
    def __init__(s, faces, kind="brep"): s.faces, s.kind = [np.asarray(f, float) for f in faces], kind
    def xf(s, M): return Mesh([(M[:3, :3] @ f.T).T + M[:3, 3] for f in s.faces], s.kind)
    def bbox(s):
        a = np.vstack(s.faces); return a.min(0), a.max(0)


class Region(object):
    """평면 영역 (Boundary Surfaces 결과): 바깥 고리 + 구멍 고리."""
    __slots__ = ("outer", "holes")
    def __init__(s, outer, holes): s.outer, s.holes = outer, holes
    def xf(s, M): return Region(s.outer.xf(M), [h.xf(M) for h in s.holes])
    def faces(s): return [s.outer.p]


def xform(g, M):
    if isinstance(g, np.ndarray): return M[:3, :3] @ g + M[:3, 3]
    if hasattr(g, "xf"): return g.xf(M)
    return g


def rot_matrix(axis, ang, center):
    a = np.asarray(axis, float); a = a / np.linalg.norm(a)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    R = np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * K @ K
    M = np.eye(4); M[:3, :3] = R; M[:3, 3] = center - R @ center; return M


def box_faces(P, x0, x1, y0, y1, z0, z1):
    c = np.array([[x, y, z] for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)], float)
    c = P.to_world(c)
    idx = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return Mesh([c[list(i)] for i in idx])


def loop_faces(loop_pts, vec):
    v = np.asarray(vec, float); faces = []
    n = len(loop_pts)
    for i in range(n):
        a, b = loop_pts[i], loop_pts[(i + 1) % n]
        faces.append(np.array([a, b, b + v, a + v]))
    return faces


def cyl_faces(P, r, h, seg=16, z0=0.0):
    ang = np.linspace(0, 2 * math.pi, seg, endpoint=False)
    ring = np.c_[r * np.cos(ang), r * np.sin(ang), np.full(seg, z0)]
    base = P.to_world(ring)
    top = base + P.z * h
    f = loop_faces(base, P.z * h) + [base[::-1], top]
    return Mesh(f)


# ------------------------------------------------------------------ 변환 (형 맞추기)
class Err(Exception):
    pass


def as_num(x):
    if isinstance(x, (bool, np.bool_)): return 1.0 if x else 0.0
    if isinstance(x, (int, float, np.floating, np.integer)): return float(x)
    if isinstance(x, str):
        try: return float(x)
        except ValueError: raise Err("'%s' → 숫자 불가" % x)
    if isinstance(x, tuple) and len(x) == 2 and x[0] == "dom": raise Err("구간 → 숫자 불가")
    raise Err("%s → 숫자 불가" % type(x).__name__)


def as_int(x): return int(round(as_num(x)))


def as_bool(x):
    if isinstance(x, str):
        if x.strip().lower() in ("true", "1"): return True
        if x.strip().lower() in ("false", "0"): return False
    return bool(as_num(x))


def as_pt(x):
    if isinstance(x, np.ndarray) and x.shape == (3,): return x
    if isinstance(x, Plane): return x.o
    if isinstance(x, Vec): return x.v.copy()
    raise Err("%s → 점 불가" % type(x).__name__)


def as_vec(x):
    if isinstance(x, Vec): return x.v
    if isinstance(x, np.ndarray) and x.shape == (3,): return x
    if isinstance(x, Plane): return x.z
    if isinstance(x, Curve) and len(x.p) == 2 and not x.closed: return x.p[1] - x.p[0]
    raise Err("%s → 벡터 불가" % type(x).__name__)


def as_plane(x):
    if isinstance(x, Plane): return x
    if isinstance(x, np.ndarray) and x.shape == (3,): return Plane.world(x)
    if isinstance(x, Curve): return x.planar_plane()
    raise Err("%s → 평면 불가" % type(x).__name__)


def as_dom(x):
    if isinstance(x, tuple) and x[0] == "dom": return x[1], x[2]
    v = as_num(x); return (0.0, v) if v >= 0 else (v, 0.0)


def as_curve(x):
    if isinstance(x, Curve): return x
    if isinstance(x, Region): return x.outer
    raise Err("%s → 곡선 불가" % type(x).__name__)


# ------------------------------------------------------------------ 컴포넌트
COMPS = {}


def comp(key, ins, outs):
    """ins: [(name, access, default)]  access: item/list/tree"""
    def deco(f):
        COMPS[key] = (ins, outs, f); return f
    return deco


NODEF = object()
ABR = [("A", "item", NODEF), ("B", "item", NODEF)]


def _arith(op):
    def f(A, B):
        if isinstance(A, (Vec, np.ndarray)) or isinstance(B, (Vec, np.ndarray)):
            a = as_vec(A) if isinstance(A, (Vec, np.ndarray)) else as_num(A)
            b = as_vec(B) if isinstance(B, (Vec, np.ndarray)) else as_num(B)
            r = op(a, b)
            return {"Result": Vec(r) if isinstance(A, Vec) or isinstance(B, Vec) else r}
        a, b = as_num(A), as_num(B)
        return {"Result": op(a, b)}
    return f


comp("Maths/Operators/Addition", ABR, ["Result"])(_arith(lambda a, b: a + b))
comp("Maths/Operators/Subtraction", ABR, ["Result"])(_arith(lambda a, b: a - b))
comp("Maths/Operators/Multiplication", ABR, ["Result"])(_arith(lambda a, b: a * b))


@comp("Maths/Operators/Division", ABR, ["Result"])
def _div(A, B):
    b = as_num(B)
    if b == 0: raise Err("0으로 나눔")
    return {"Result": as_num(A) / b}


@comp("Maths/Operators/Modulus", ABR, ["Result"])
def _mod(A, B): return {"Result": math.fmod(as_num(A), as_num(B)) % as_num(B)}


@comp("Maths/Trig/Radians", [("Degrees", "item", NODEF)], ["Radians"])
def _rad(Degrees): return {"Radians": math.radians(as_num(Degrees))}


@comp("Maths/Domain/Construct Domain", [("Domain start", "item", 0.0), ("Domain end", "item", 1.0)], ["Domain"])
def _cdom(**k): return {"Domain": ("dom", as_num(k["Domain start"]), as_num(k["Domain end"]))}


@comp("Sets/Sequence/Series", [("Start", "item", 0.0), ("Step", "item", 1.0), ("Count", "item", 10)], ["Series"])
def _series(Start, Step, Count):
    s, d, c = as_num(Start), as_num(Step), as_int(Count)
    return {"Series": [s + d * i for i in range(max(c, 0))]}


@comp("Sets/Sequence/Range", [("Domain", "item", ("dom", 0.0, 1.0)), ("Steps", "item", 10)], ["Range"])
def _range(Domain, Steps):
    a, b = as_dom(Domain); n = as_int(Steps)
    return {"Range": [a + (b - a) * i / n for i in range(n + 1)] if n > 0 else [a]}


@comp("Sets/List/List Length", [("List", "list", NODEF)], ["Length"])
def _llen(List): return {"Length": len(List)}


@comp("Sets/List/Shift List", [("List", "list", NODEF), ("Shift", "item", 1), ("Wrap", "item", True)], ["List"])
def _shift(List, Shift, Wrap):
    s = as_int(Shift); n = len(List)
    if as_bool(Wrap): return {"List": [List[(i + s) % n] for i in range(n)]}
    return {"List": [List[i + s] for i in range(n) if 0 <= i + s < n]}


@comp("Sets/List/Dispatch", [("List", "list", NODEF), ("Dispatch pattern", "list", [True, False])], ["List A", "List B"])
def _dispatch(**k):
    L, P = k["List"], [as_bool(p) for p in k["Dispatch pattern"]]
    A = [x for i, x in enumerate(L) if P[i % len(P)]]
    Bl = [x for i, x in enumerate(L) if not P[i % len(P)]]
    return {"List A": A, "List B": Bl}


@comp("Vector/Point/Construct Point", [("X coordinate", "item", 0.0), ("Y coordinate", "item", 0.0), ("Z coordinate", "item", 0.0)], ["Point"])
def _cpt(**k): return {"Point": np.array([as_num(k["X coordinate"]), as_num(k["Y coordinate"]), as_num(k["Z coordinate"])])}


@comp("Vector/Point/Deconstruct", [("Point", "item", NODEF)], ["X component", "Y component", "Z component"])
def _dpt(Point):
    p = as_pt(Point); return {"X component": p[0], "Y component": p[1], "Z component": p[2]}


@comp("Vector/Plane/XY Plane", [("Origin", "item", np.zeros(3))], ["Plane"])
def _xy(Origin): return {"Plane": Plane.world(as_pt(Origin))}


@comp("Vector/Plane/Construct Plane", [("Origin", "item", np.zeros(3)), ("X-Axis", "item", Vec((1, 0, 0))), ("Y-Axis", "item", Vec((0, 1, 0)))], ["Plane"])
def _cpl(**k):
    x, y = as_vec(k["X-Axis"]), as_vec(k["Y-Axis"])
    if np.linalg.norm(np.cross(x, y)) < 1e-9: raise Err("X·Y축 평행")
    return {"Plane": Plane(as_pt(k["Origin"]), x, y)}


def perp_to(z):
    z = z / np.linalg.norm(z)
    # RhinoCommon Vector3d.PerpendicularTo 와 같은 규칙
    if abs(z[0]) <= abs(z[1]) and abs(z[0]) <= abs(z[2]) and False: pass
    x, y, zz = z
    if abs(x) > abs(y) * 0 and (abs(zz) >= abs(x) or abs(zz) >= abs(y)) and False: pass
    if (x != 0 and y != 0) or (x != 0 and zz != 0) or (y != 0 and zz != 0):
        if abs(x) <= abs(y) and abs(x) <= abs(zz): p = np.array([0, zz, -y])
        elif abs(y) <= abs(x) and abs(y) <= abs(zz): p = np.array([zz, 0, -x])
        else: p = np.array([y, -x, 0])
    else:
        p = np.array([1.0, 0, 0]) if abs(x) < 1e-12 else np.array([0, 1.0, 0])
    return p / np.linalg.norm(p)


@comp("Vector/Plane/Plane Normal", [("Origin", "item", np.zeros(3)), ("Z-Axis", "item", Vec((0, 0, 1)))], ["Plane"])
def _pn(**k):
    z = as_vec(k["Z-Axis"])
    if np.linalg.norm(z) < 1e-9: raise Err("Z축 길이 0")
    z = z / np.linalg.norm(z); x = perp_to(z)
    return {"Plane": Plane(as_pt(k["Origin"]), x, np.cross(z, x))}


@comp("Vector/Plane/Align Plane", [("Plane", "item", NODEF), ("Direction", "item", NODEF)], ["Plane", "Angle"])
def _al(Plane_=None, **k):
    P = as_plane(k["Plane"]); d = as_vec(k["Direction"])
    dp = d - P.z * (d @ P.z)
    if np.linalg.norm(dp) < 1e-9: return {"Plane": P, "Angle": 0.0}
    x = dp / np.linalg.norm(dp)
    ang = math.atan2(np.cross(P.x, x) @ P.z, P.x @ x)
    return {"Plane": Plane(P.o, x, np.cross(P.z, x)), "Angle": ang}


for _a, _v in (("X", (1, 0, 0)), ("Y", (0, 1, 0)), ("Z", (0, 0, 1))):
    def _mk(v):
        return lambda Factor: {"Unit vector": Vec(np.array(v, float) * as_num(Factor))}
    comp("Vector/Vector/Unit " + _a, [("Factor", "item", 1.0)], ["Unit vector"])(_mk(_v))


@comp("Vector/Vector/Vector 2Pt", [("Point A", "item", NODEF), ("Point B", "item", NODEF), ("Unitize", "item", False)], ["Vector", "Length"])
def _v2(**k):
    v = as_pt(k["Point B"]) - as_pt(k["Point A"]); L = float(np.linalg.norm(v))
    if as_bool(k["Unitize"]) and L > 0: v = v / L
    return {"Vector": Vec(v), "Length": L}


@comp("Vector/Vector/Vector XYZ", [("X component", "item", 0.0), ("Y component", "item", 0.0), ("Z component", "item", 0.0)], ["Vector", "Length"])
def _vxyz(**k):
    v = np.array([as_num(k["X component"]), as_num(k["Y component"]), as_num(k["Z component"])])
    return {"Vector": Vec(v), "Length": float(np.linalg.norm(v))}


@comp("Vector/Vector/Reverse", [("Vector", "item", NODEF)], ["Vector"])
def _rev(Vector): return {"Vector": Vec(-as_vec(Vector))}


def _geo_xf(G, M):
    if isinstance(G, (int, float, str)): raise Err("숫자는 변형 불가")
    return xform(G, M)


@comp("Transform/Euclidean/Move", [("Geometry", "item", NODEF), ("Motion", "item", Vec((0, 0, 10)))], ["Geometry", "Transform"])
def _move(Geometry, Motion):
    M = np.eye(4); M[:3, 3] = as_vec(Motion); return {"Geometry": _geo_xf(Geometry, M), "Transform": M}


@comp("Transform/Euclidean/Rotate", [("Geometry", "item", NODEF), ("Angle", "item", 0.5 * math.pi), ("Plane", "item", Plane.world())], ["Geometry", "Transform"])
def _rot(Geometry, Angle, Plane_=None, **k):
    P = as_plane(k["Plane"]); M = rot_matrix(P.z, as_num(Angle), P.o)
    return {"Geometry": _geo_xf(Geometry, M), "Transform": M}


@comp("Transform/Affine/Scale", [("Geometry", "item", NODEF), ("Center", "item", np.zeros(3)), ("Factor", "item", 0.5)], ["Geometry", "Transform"])
def _scale(Geometry, Center, Factor):
    c = as_pt(Center); f = as_num(Factor); M = np.eye(4) * f; M[3, 3] = 1; M[:3, 3] = c - f * c
    return {"Geometry": _geo_xf(Geometry, M), "Transform": M}


@comp("Transform/Euclidean/Orient", [("Geometry", "item", NODEF), ("Source", "item", NODEF), ("Target", "item", NODEF)], ["Geometry", "Transform"])
def _orient(Geometry, Source, Target):
    M = as_plane(Target).matrix() @ np.linalg.inv(as_plane(Source).matrix())
    return {"Geometry": _geo_xf(Geometry, M), "Transform": M}


@comp("Curve/Primitive/Polygon", [("Plane", "item", Plane.world()), ("Radius", "item", 1.0), ("Segments", "item", 6), ("Fillet Radius", "item", 0.0)], ["Polygon", "Length"])
def _poly(**k):
    P = as_plane(k["Plane"]); r = as_num(k["Radius"]); n = as_int(k["Segments"])
    if n < 3: raise Err("Segments < 3")
    a = np.arange(n) * 2 * math.pi / n
    c = Curve(P.to_world(np.c_[r * np.cos(a), r * np.sin(a), np.zeros(n)]), True)
    return {"Polygon": c, "Length": c.length()}


@comp("Curve/Primitive/Rectangle", [("Plane", "item", Plane.world()), ("X Size", "item", ("dom", 0.0, 10.0)), ("Y Size", "item", ("dom", 0.0, 5.0)), ("Radius", "item", 0.0)], ["Rectangle", "Length"])
def _rect(**k):
    P = as_plane(k["Plane"]); x0, x1 = as_dom(k["X Size"]); y0, y1 = as_dom(k["Y Size"])
    c = Curve(P.to_world(np.array([[x0, y0, 0], [x1, y0, 0], [x1, y1, 0], [x0, y1, 0]], float)), True)
    return {"Rectangle": c, "Length": c.length()}


@comp("Curve/Primitive/Line", [("Start Point", "item", NODEF), ("End Point", "item", NODEF)], ["Line"])
def _line(**k): return {"Line": Curve([as_pt(k["Start Point"]), as_pt(k["End Point"])])}


@comp("Curve/Primitive/Line SDL", [("Start", "item", np.zeros(3)), ("Direction", "item", Vec((0, 0, 1))), ("Length", "item", 1.0)], ["Line"])
def _lsdl(Start, Direction, Length):
    d = as_vec(Direction); d = d / np.linalg.norm(d); s = as_pt(Start)
    return {"Line": Curve([s, s + d * as_num(Length)])}


@comp("Curve/Primitive/Arc 3Pt", [("Point A", "item", NODEF), ("Point B", "item", NODEF), ("Point C", "item", NODEF)], ["Arc", "Plane", "Radius"])
def _arc3(**k):
    a, b, c = as_pt(k["Point A"]), as_pt(k["Point B"]), as_pt(k["Point C"])
    ab, ac = b - a, c - a; n = np.cross(ab, ac)
    if np.linalg.norm(n) < 1e-9: raise Err("세 점이 일직선")
    cc = a + (np.cross(n, ab) * (ac @ ac) + np.cross(ac, n) * (ab @ ab)) / (2 * (n @ n))
    r = float(np.linalg.norm(a - cc)); P = Plane(cc, a - cc, np.cross(n, a - cc))
    def ang(p):
        q = p - cc; return math.atan2(q @ P.y, q @ P.x) % (2 * math.pi)
    tb, tc = ang(b), ang(c)
    end = tc if tb < tc else tc  # a→b→c 방향
    if not tb < tc: P = Plane(cc, a - cc, -np.cross(n, a - cc)); tc = ang(c)
    t = np.linspace(0, tc, 32)
    return {"Arc": Curve(P.to_world(np.c_[r * np.cos(t), r * np.sin(t), np.zeros(32)])), "Plane": P, "Radius": r}


@comp("Curve/Spline/PolyLine", [("Vertices", "list", NODEF), ("Closed", "item", False)], ["Polyline"])
def _pl(Vertices, Closed):
    pts = [as_pt(v) for v in Vertices]
    if len(pts) < 2: raise Err("점 2개 미만")
    return {"Polyline": Curve(pts, as_bool(Closed))}


@comp("Curve/Util/Explode", [("Curve", "item", NODEF), ("Recursive", "item", True)], ["Segments", "Vertices"])
def _explode(Curve_=None, **k):
    c = as_curve(k["Curve"]); v = c.verts()
    return {"Segments": c.segs(), "Vertices": [p for p in (c.p if c.closed else v)]}


@comp("Curve/Analysis/Length", [("Curve", "item", NODEF)], ["Length"])
def _len(**k): return {"Length": as_curve(k["Curve"]).length()}


@comp("Curve/Analysis/End Points", [("Curve", "item", NODEF)], ["Start", "End"])
def _ends(**k):
    v = as_curve(k["Curve"]).verts(); return {"Start": v[0], "End": v[-1]}


@comp("Curve/Analysis/Evaluate Length", [("Curve", "item", NODEF), ("Length", "item", 0.5), ("Normalized", "item", True)], ["Point", "Tangent", "Parameter"])
def _evl(**k):
    c = as_curve(k["Curve"]); L = as_num(k["Length"]); tot = c.length()
    if as_bool(k["Normalized"]): L = L * tot
    if L < -1e-6 or L > tot + 1e-6:
        raise Err("길이 %.0f 가 곡선 길이 %.0f 밖" % (L, tot))
    t = c.param_at_length(L); p, d = c.at_param(t)
    return {"Point": p, "Tangent": Vec(d), "Parameter": t}


@comp("Curve/Analysis/Curve Closest Point", [("Point", "item", NODEF), ("Curve", "item", NODEF)], ["Point", "Parameter", "Distance"])
def _ccp(**k):
    p = as_pt(k["Point"]); c = as_curve(k["Curve"]); v = c.verts(); best = None
    for i in range(len(v) - 1):
        a, b = v[i], v[i + 1]; d = b - a; L2 = d @ d
        f = 0.0 if L2 == 0 else min(max((p - a) @ d / L2, 0), 1)
        q = a + f * d; dist = np.linalg.norm(p - q)
        if best is None or dist < best[0]: best = (dist, q, i + f)
    return {"Point": best[1], "Parameter": best[2], "Distance": best[0]}


@comp("Curve/Division/Divide Curve", [("Curve", "item", NODEF), ("Count", "item", 10), ("Kinks", "item", False)], ["Points", "Tangents", "Parameters"])
def _divc(**k):
    c = as_curve(k["Curve"]); n = as_int(k["Count"]); tot = c.length()
    m = n if c.closed else n + 1
    P, T, Pa = [], [], []
    for i in range(m):
        t = c.param_at_length(tot * i / n); p, d = c.at_param(t); P.append(p); T.append(Vec(d)); Pa.append(t)
    return {"Points": P, "Tangents": T, "Parameters": Pa}


@comp("Curve/Division/Divide Length", [("Curve", "item", NODEF), ("Length", "item", 1.0)], ["Points", "Tangents", "Parameters"])
def _divl(**k):
    c = as_curve(k["Curve"]); L = as_num(k["Length"]); tot = c.length()
    if L <= 0: raise Err("길이 0")
    P, T, Pa = [], [], []
    x = 0.0
    while x <= tot + 1e-6:
        t = c.param_at_length(x); p, d = c.at_param(t); P.append(p); T.append(Vec(d)); Pa.append(t); x += L
    return {"Points": P, "Tangents": T, "Parameters": Pa}


@comp("Curve/Division/Shatter", [("Curve", "item", NODEF), ("Parameters", "list", NODEF)], ["Segments"])
def _shatter(Parameters, **k):
    c = as_curve(k["Curve"]); ts = sorted(set(round(as_num(t), 9) for t in Parameters))
    v = c.verts(); n = len(v) - 1
    def sub(t0, t1):
        pts = [c.at_param(t0)[0]]
        for i in range(int(math.floor(t0)) + 1, int(math.ceil(t1))):
            if t0 < i < t1: pts.append(v[i])
        pts.append(c.at_param(t1)[0]); return Curve(pts)
    if c.closed:
        if not ts: return {"Segments": [c]}
        out = []
        for i in range(len(ts)):
            a, b = ts[i], (ts[i + 1] if i + 1 < len(ts) else ts[0] + n)
            if b <= n: out.append(sub(a, b))
            else:
                p1 = sub(a, n); p2 = sub(0, b - n); out.append(Curve(np.vstack([p1.p, p2.p[1:]])))
        return {"Segments": out}
    cuts = [0.0] + [t for t in ts if 0 < t < n] + [float(n)]
    return {"Segments": [sub(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]}


@comp("Intersect/Shape/Region Union", [("Curves", "list", NODEF), ("Plane", "item", None)], ["Result"])
def _runion(Curves, **k):
    from shapely.geometry import Polygon as SP
    from shapely.ops import unary_union
    cs = [as_curve(c) for c in Curves]
    P = as_plane(k.get("Plane")) if k.get("Plane") is not None else cs[0].planar_plane()
    M = np.linalg.inv(P.matrix())
    polys = []
    for c in cs:
        q = (M[:3, :3] @ c.p.T).T + M[:3, 3]; polys.append(SP(q[:, :2]).buffer(0))
    u = unary_union(polys); out = []
    for g in (u.geoms if hasattr(u, "geoms") else [u]):
        xy = np.array(g.exterior.coords)[:-1]
        out.append(Curve(P.to_world(np.c_[xy, np.zeros(len(xy))]), True))
    return {"Result": out}


@comp("Surface/Freeform/Boundary Surfaces", [("Edges", "list", NODEF)], ["Surfaces"])
def _bsrf(Edges):
    from shapely.geometry import Polygon as SP
    cs = [as_curve(c) for c in Edges]
    for c in cs:
        if not c.closed: raise Err("열린 곡선")
    P = cs[0].planar_plane(); M = np.linalg.inv(P.matrix())
    sp = [SP(((M[:3, :3] @ c.p.T).T + M[:3, 3])[:, :2]) for c in cs]
    order = sorted(range(len(cs)), key=lambda i: -sp[i].area); used = set(); out = []
    for i in order:
        if i in used: continue
        used.add(i); holes = []
        for j in order:
            if j not in used and sp[i].contains(sp[j]): holes.append(cs[j]); used.add(j)
        out.append(Region(cs[i], holes))
    return {"Surfaces": out}


@comp("Surface/Freeform/Extrude", [("Base", "item", NODEF), ("Direction", "item", Vec((0, 0, 1)))], ["Extrusion"])
def _extrude(Base, Direction):
    v = as_vec(Direction)
    if isinstance(Base, Region):
        f = []
        for loop in [Base.outer] + Base.holes: f += loop_faces(loop.p, v)
        f += [Base.outer.p, Base.outer.p + v]
        return {"Extrusion": Mesh(f)}
    c = as_curve(Base)
    f = loop_faces(c.p, v) if c.closed else [np.array([c.p[i], c.p[i + 1], c.p[i + 1] + v, c.p[i] + v]) for i in range(len(c.p) - 1)]
    if c.closed: f += [c.p, c.p + v]
    return {"Extrusion": Mesh(f)}


@comp("Surface/Freeform/Pipe", [("Curve", "item", NODEF), ("Radius", "item", 1.0), ("Caps", "item", 0), ("Fit Rail", "item", True)], ["Pipe"])
def _pipe(**k):
    c = as_curve(k["Curve"]); r = as_num(k["Radius"]); f = []
    for s in c.segs():
        a, b = s.p; d = b - a
        if np.linalg.norm(d) < 1e-9: continue
        x = perp_to(d / np.linalg.norm(d)); P = Plane(a, x, np.cross(d / np.linalg.norm(d), x))
        f += cyl_faces(P, r, float(np.linalg.norm(d)), 10).faces
    return {"Pipe": [Mesh(f)]}


@comp("Surface/Primitive/Box 2Pt", [("Point A", "item", np.zeros(3)), ("Point B", "item", np.ones(3)), ("Plane", "item", Plane.world())], ["Box"])
def _box2(**k):
    P = as_plane(k["Plane"]); M = np.linalg.inv(P.matrix())
    a = M[:3, :3] @ as_pt(k["Point A"]) + M[:3, 3]; b = M[:3, :3] @ as_pt(k["Point B"]) + M[:3, 3]
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    if np.any(hi - lo < 1e-9): raise Err("두께 0인 상자")
    return {"Box": box_faces(P, lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])}


@comp("Surface/Primitive/Center Box", [("Base", "item", Plane.world()), ("X", "item", 1.0), ("Y", "item", 1.0), ("Z", "item", 1.0)], ["Box"])
def _cbox(**k):
    P = as_plane(k["Base"]); x, y, z = as_num(k["X"]), as_num(k["Y"]), as_num(k["Z"])
    return {"Box": box_faces(P, -x, x, -y, y, -z, z)}


@comp("Surface/Primitive/Cylinder", [("Base", "item", Plane.world()), ("Radius", "item", 1.0), ("Length", "item", 1.0)], ["Cylinder"])
def _cyl(**k): return {"Cylinder": cyl_faces(as_plane(k["Base"]), as_num(k["Radius"]), as_num(k["Length"]))}


@comp("Surface/Primitive/Sphere", [("Base", "item", Plane.world()), ("Radius", "item", 1.0)], ["Sphere"])
def _sph(**k):
    P = as_plane(k["Base"]); r = as_num(k["Radius"]); f = []
    la = np.linspace(-math.pi / 2, math.pi / 2, 7); lo = np.linspace(0, 2 * math.pi, 13)
    for i in range(6):
        for j in range(12):
            q = [(la[i], lo[j]), (la[i], lo[j + 1]), (la[i + 1], lo[j + 1]), (la[i + 1], lo[j])]
            f.append(P.to_world(np.array([[r * math.cos(a) * math.cos(b), r * math.cos(a) * math.sin(b), r * math.sin(a)] for a, b in q])))
    return {"Sphere": Mesh(f)}


@comp("Surface/Util/Cap Holes", [("Brep", "item", NODEF)], ["Brep"])
def _cap(Brep): return {"Brep": Brep}


# 트리 접근 컴포넌트 (특별 처리)
TREE_COMPS = {"Sets/Tree/Merge", "Sets/Tree/Flip Matrix"}


# ------------------------------------------------------------------ 데이터 트리 실행
def graft(tree):
    out = OrderedDict()
    for p, items in tree.items():
        for i, x in enumerate(items): out[p + (i,)] = [x]
    return out


def flatten(tree):
    return OrderedDict([((0,), [x for items in tree.values() for x in items])])


def run_tree_comp(key, ins):
    if key == "Sets/Tree/Merge":
        out = OrderedDict()
        for name in ("Data 1", "Data 2"):
            for p, items in ins.get(name, {}).items(): out.setdefault(p, []).extend(items)
        return {"Result": out}
    if key == "Sets/Tree/Flip Matrix":
        t = ins["Data"]; br = list(t.values()); paths = list(t.keys())
        if not br: return {"Data": OrderedDict()}
        n = max(len(b) for b in br)
        pre = paths[0][:-1] if len(paths[0]) > 1 else ()
        out = OrderedDict()
        for j in range(n): out[pre + (j,)] = [b[j] for b in br if j < len(b)]
        return {"Data": out}


def run_comp(key, ins_spec, outs, f, trees, msgs):
    """trees: name → OrderedDict(path → list)."""
    tr = {}
    for name, acc, default in ins_spec:
        t = trees.get(name)
        if not t or all(len(v) == 0 for v in t.values()):
            if default is NODEF:
                msgs.append(("warning", "입력 '%s' 비어 있음" % name)); return {o: OrderedDict() for o in outs}
            if default is None:
                t = OrderedDict([((0,), [None])])
            else:
                t = OrderedDict([((0,), list(default) if acc == "list" and isinstance(default, list) else [default])])
        tr[name] = t
    nb = max(len(t) for t in tr.values())
    master = next(n for n, a, d in ins_spec if len(tr[n]) == nb)
    mpaths = list(tr[master].keys())
    out = {o: OrderedDict() for o in outs}
    nerr = 0
    for b in range(nb):
        path = mpaths[b]
        br = {}
        for name, acc, d in ins_spec:
            vals = list(tr[name].values()); br[name] = vals[min(b, len(vals) - 1)]
        items = [n for n, a, d in ins_spec if a == "item"]
        if any(len(br[n]) == 0 for n in br): continue
        n_it = max([len(br[n]) for n in items] or [1])
        res = []
        for i in range(n_it):
            kw = {}
            for name, acc, d in ins_spec:
                kw[name] = br[name] if acc == "list" else br[name][min(i, len(br[name]) - 1)]
            try:
                res.append(call(f, kw))
            except Err as ex:
                nerr += 1
                if nerr <= 3: msgs.append(("error", str(ex)))
                res.append(None)
        for o in outs:
            for i, r in enumerate(res):
                if r is None: continue
                v = r.get(o)
                if isinstance(v, list):
                    p = path + (i,) if n_it > 1 else path
                    out[o].setdefault(p, []).extend(v)
                elif v is not None:
                    out[o].setdefault(path, []).append(v)
                else:
                    out[o].setdefault(path, [])
    if nerr > 3: msgs.append(("error", "… 외 %d건 더" % (nerr - 3)))
    return out


def call(f, kw):
    return f(**kw)


# ------------------------------------------------------------------ 그래프 실행
class Sim(object):
    def __init__(self, graph, catalog=None):
        self.g = B.normalize_graph(graph)
        self.nodes = OrderedDict((n["id"], n) for n in self.g["nodes"])
        self.out = {}
        self.msgs = {}
        self.cat = catalog

    def param_value(self, n):
        c = n["component"]
        if c.endswith("Number Slider"):
            v = n.get("slider_value", 0); return [int(round(v)) if n.get("slider_integer") else float(v)]
        if c.endswith("Boolean Toggle"): return [bool(n.get("toggle"))]
        if c.endswith("Panel"):
            vals = []
            for line in (n.get("text") or "").splitlines():
                s = line.strip()
                if not s: continue
                try: vals.append(float(s))
                except ValueError: vals.append(s)
            return vals
        return []

    def resolve_key(self, c):
        if c in COMPS or c in TREE_COMPS or c.startswith("Params/"): return c
        name = c.split("/")[-1]
        cands = [k for k in list(COMPS) + list(TREE_COMPS) if k.split("/")[-1] == name]
        return cands[0] if len(cands) == 1 else c

    def run(self):
        incoming = {}
        for w in self.g["wires"]: incoming.setdefault(w["to_node"], []).append(w)
        done = set(); order = []
        ids = list(self.nodes)
        while len(done) < len(ids):
            prog = False
            for i in ids:
                if i in done: continue
                if all(w["from_node"] in done or w["from_node"] not in self.nodes for w in incoming.get(i, [])):
                    order.append(i); done.add(i); prog = True
            if not prog: raise RuntimeError("순환 연결")
        for nid in order:
            n = self.nodes[nid]; key = self.resolve_key(n["component"]); msgs = self.msgs.setdefault(nid, [])
            if key.startswith("Params/"):
                t = OrderedDict([((0,), self.param_value(n))])
                for w in incoming.get(nid, []):
                    t = self.fetch(w)
                self.out[nid] = {"": t}; continue
            trees = {}
            for w in incoming.get(nid, []):
                src = self.fetch(w)
                name = self.in_name(key, w["to_input"])
                if name in trees:
                    for p, it in src.items(): trees[name].setdefault(p, []).extend(it)
                else:
                    trees[name] = src
            if key in TREE_COMPS:
                self.out[nid] = run_tree_comp(key, trees)
            elif key in COMPS:
                ins, outs, f = COMPS[key]
                self.out[nid] = run_comp(key, ins, outs, f, trees, msgs)
            else:
                msgs.append(("error", "검사기에 없는 컴포넌트 %s" % key)); self.out[nid] = {}
        return self

    def in_name(self, key, ref):
        ins = COMPS[key][0] if key in COMPS else [("Data 1",), ("Data 2",)] if key.endswith("Merge") else [("Data",)]
        names = [i[0] for i in ins]
        i = B.match_param([(n, n) for n in names], ref)
        return names[i] if i is not None else ref

    def fetch(self, w):
        o = self.out.get(w["from_node"], {})
        n = self.nodes[w["from_node"]]; key = self.resolve_key(n["component"])
        if key.startswith("Params/"): t = o.get("", OrderedDict())
        else:
            names = list(o.keys())
            i = B.match_param([(x, x) for x in names], w.get("from_output"))
            t = o[names[i]] if i is not None else OrderedDict()
        m = w.get("mapping", "none")
        if m == "graft": t = graft(t)
        elif m == "flatten": t = flatten(t)
        return t

    def items(self, nid, out=None):
        o = self.out.get(nid, {})
        if not o: return []
        t = o[out] if out else next(iter(o.values()))
        return [x for v in t.values() for x in v]

    def problems(self):
        r = []
        for nid, ms in self.msgs.items():
            for lv, m in ms:
                r.append("%s %s (%s): %s" % (lv.upper(), nid, self.nodes[nid].get("nickname") or self.nodes[nid]["component"].split("/")[-1], m))
        return r

    # ---- Bake 흉내: (면 목록, 재료) ----
    def baked(self):
        geo = []
        for nid in B.bake_targets(self.g):
            mat = self.nodes[nid].get("material", "")
            for x in self.items(nid): geo.append((x, mat, nid))
        for bl in self.g.get("blocks", []):
            parts = []
            for pid in bl["parts"]:
                for x in self.items(pid): parts.append((x, self.nodes[pid].get("material", ""), pid))
            planes = [p if isinstance(p, Plane) else Plane.world(p) for p in self.items(bl["at"])
                      if isinstance(p, Plane) or (isinstance(p, np.ndarray) and p.shape == (3,))]
            for P in planes:
                M = P.matrix()
                for x, mat, pid in parts: geo.append((xform(x, M), mat, bl["name"]))
        return geo


# ------------------------------------------------------------------ 그리기
MATCOL = {"steel": (95, 100, 110), "concrete": (200, 198, 192), "glass": (150, 185, 215), "aluminum": (175, 178, 182),
          "spandrel": (70, 75, 82), "wood": (170, 130, 90), "stone": (190, 180, 165), "": (160, 160, 160)}


def faces_of(x):
    if isinstance(x, Mesh): return x.faces
    if isinstance(x, Region): return x.faces()
    return []


def lines_of(x):
    if isinstance(x, Curve): return [x.verts()]
    return []


def render(geo, path, size=(1600, 1600), eye_dir=(1.0, -1.3, 0.55), fov=1.0, target=None, dist=None, clip_box=None, title=""):
    from PIL import Image, ImageDraw
    F, C, L = [], [], []
    for x, mat, _ in geo:
        for f in faces_of(x):
            if clip_box is not None and not (np.all(f.min(0) >= clip_box[0]) and np.all(f.max(0) <= clip_box[1])): continue
            F.append(f); C.append(MATCOL.get(mat, MATCOL[""]))
        for l in lines_of(x): L.append(l)
    if not F and not L: return 0
    allp = np.vstack(F + L)
    lo, hi = allp.min(0), allp.max(0)
    tgt = np.asarray(target, float) if target is not None else (lo + hi) / 2
    ed = np.asarray(eye_dir, float); ed /= np.linalg.norm(ed)
    R = np.linalg.norm(hi - lo) / 2
    d = dist if dist else R / math.tan(fov / 2) * 1.05
    eye = tgt + ed * d
    fw = -ed; up = np.array([0, 0, 1.0]); rt = np.cross(fw, up); rt /= np.linalg.norm(rt); up2 = np.cross(rt, fw)
    W, H = size; foc = (W / 2) / math.tan(fov / 2)
    light = np.array([0.5, -0.8, 0.9]); light /= np.linalg.norm(light)
    items = []
    for f, c in zip(F, C):
        q = f - eye; z = q @ fw
        if np.any(z <= 1): continue
        sx = W / 2 + foc * (q @ rt) / z; sy = H / 2 - foc * (q @ up2) / z
        n = np.cross(f[1] - f[0], f[2] - f[0]) if len(f) >= 3 else np.zeros(3)
        if len(f) > 3:
            n = np.zeros(3)
            for i in range(len(f)):
                a, b = f[i], f[(i + 1) % len(f)]
                n += np.array([(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])])
        nn = np.linalg.norm(n)
        sh = 0.55 + 0.45 * abs(n @ light) / nn if nn > 0 else 0.7
        col = tuple(int(min(255, ch * sh)) for ch in c)
        items.append((float(z.mean()), list(zip(sx.tolist(), sy.tolist())), col))
    items.sort(key=lambda t: -t[0])
    im = Image.new("RGB", (W, H), (250, 250, 250)); dr = ImageDraw.Draw(im)
    for _, pts, col in items:
        if len(pts) >= 3: dr.polygon(pts, fill=col, outline=tuple(max(0, v - 35) for v in col))
    for l in L:
        q = l - eye; z = q @ fw
        if np.any(z <= 1): continue
        sx = W / 2 + foc * (q @ rt) / z; sy = H / 2 - foc * (q @ up2) / z
        dr.line(list(zip(sx.tolist(), sy.tolist())), fill=(40, 90, 200), width=1)
    if title: dr.text((20, 20), title, fill=(0, 0, 0))
    im.save(path)
    return len(items)


if __name__ == "__main__":
    g = json.load(open(sys.argv[1], encoding="utf-8"))
    s = Sim(g).run()
    for p in s.problems(): print(p)
    geo = s.baked()
    print("bake geometry:", len(geo))
    if len(sys.argv) > 2:
        print("faces:", render(geo, sys.argv[2]))
