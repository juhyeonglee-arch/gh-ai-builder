# 08 비틀린 다이아그리드 타워 v3 — 구조 + 커튼월을 처음부터 한 정의로 다시 짠 것
# 바뀐 점(07 대비):
#  - 부재 끝점을 mm로 잰다 (Evaluate Length Normalized=False). 07은 비율로 재서 구조 전체가 오류였음.
#  - 외피(커튼월) 선 → 안쪽으로 슬래브 끝, 더 안쪽으로 다이아그리드 중심선. 구조가 유리를 뚫지 않는다.
#  - 슬래브는 층 높이에서 아래로 두께만큼, 링 보·절점·바닥 보는 슬래브 밑에 매달린다.
#  - 주강 노드는 바깥 방향 축(원반형)으로 놓여 대각재가 드럼 테두리에 정확히 닿는다.
#  - 커튼월 모서리 빈틈을 코너 기둥 블록으로 메운다.
import sys; sys.path.insert(0, ".")
from ghgen import G, graft
g = G()
ADD, SUB, MUL, DIV = "Addition", "Subtraction", "Multiplication", "Division"
POLY = "Curve/Primitive/Polygon"; UZ = "Vector/Vector/Unit Z"; EXT = "Surface/Freeform/Extrude"; MRG = "Sets/Tree/Merge"
XY = "Vector/Plane/XY Plane"; CPT = "Vector/Point/Construct Point"; CYL = "Surface/Primitive/Cylinder"; BOX2 = "Surface/Primitive/Box 2Pt"
DOM = "Maths/Domain/Construct Domain"; RECT = "Curve/Primitive/Rectangle"; EVL = "Curve/Analysis/Evaluate Length"
ROT = "Transform/Euclidean/Rotate"; MOVE = "Transform/Euclidean/Move"; SER = "Sets/Sequence/Series"


def neg(i, x, nick=""): return g.op(i, MUL, x, pNeg, nick)
def half(i, x, nick=""): return g.op(i, DIV, x, p2, nick)


# ---------------- 1. 입력 ----------------
g.group("g1", "1. 입력 — 타워", "층·평면·비틀림·다이아그리드 모듈, 그리고 외피에서 슬래브 끝·구조 중심까지 들어가는 거리를 정해요.")
sN = g.S("sN", "층수", 8, 80, 50); sH = g.S("sH", "층고", 3000, 6000, 4000)
sS = g.S("sS", "외피 한 변(유리 선)", 20000, 60000, 36000)
sT = g.S("sT", "총 비틀림(도)", 0, 120, 60)
sM = g.S("sM", "다이아그리드 모듈(층)", 2, 8, 4); sD = g.S("sD", "한 면당 칸 수", 3, 12, 6)
sIn = g.S("sIn", "유리 → 슬래브 끝 거리", 50, 600, 150)
cIn = g.S("cIn", "유리 → 다이아그리드 중심 거리", 800, 3000, 1800)
sC = g.S("sC", "코어 한 변", 6000, 20000, 12000); sCt = g.S("sCt", "코어 벽 두께", 200, 1000, 500)
sT2 = g.S("sT2", "슬래브 두께", 150, 500, 250)
p0 = g.P("p0", "0"); p1 = g.P("p1", "1"); p2 = g.P("p2", "2"); p4 = g.P("p4", "4"); pR = g.P("pR", "0.70710678", "√2/2"); pNeg = g.P("pNeg", "-1")
tog = g.T("tog", "비율로 재기(켬)", True); tAbs = g.T("tAbs", "mm로 재기(끔)", False); tgFl = g.T("tgFl", "바닥 보 켜기", False)

g.group("g1b", "1b. 입력 — 구조 부재", "대각재 H형강, 링 보·바닥 보 비율, 주강 노드, 엔드 플레이트·볼트 치수예요.")
dD = g.S("dD", "대각재 춤(바깥 방향)", 400, 1200, 700); dB = g.S("dB", "대각재 플랜지 폭", 200, 800, 450)
dTf = g.S("dTf", "플랜지 두께", 16, 100, 45); dTw = g.S("dTw", "웨브 두께", 12, 80, 30)
kR = g.S("kR", "링 보 단면 비율", 0.3, 1.0, 0.7, False); kF = g.S("kF", "바닥 보 단면 비율", 0.2, 0.8, 0.5, False); fN = g.S("fN", "한 면당 바닥 보 수", 2, 20, 8)
nD = g.S("nD", "주강 노드 지름", 600, 2500, 1300); nT = g.S("nT", "주강 노드 두께(바깥 방향)", 500, 2000, 1000)
tp = g.S("tp", "엔드 플레이트 두께", 20, 100, 50); eB = g.S("eB", "플레이트 여유", 60, 250, 120); bd = g.S("bd", "볼트 지름", 16, 48, 30)
p06 = g.P("p06", "0.6"); p045 = g.P("p045", "0.45"); p115 = g.P("p115", "1.15"); p95 = g.P("p95", "0.95")
p60 = g.P("p60", "60"); p30 = g.P("p30", "30"); p25 = g.P("p25", "25"); p20 = g.P("p20", "20"); p6 = g.P("p6", "6")

g.group("g1c", "1c. 입력 — 커튼월", "한 변 패널 수, 멀리언·트랜섬·캡, 스팬드럴 높이, 유리 두께, 패널이 층 바닥보다 내려오는 길이예요.")
nP = g.S("nP", "한 변 패널 수", 8, 60, 24); mw = g.S("mw", "멀리언 폭(맞댄 두 쪽 합)", 40, 200, 80); md = g.S("md", "멀리언 깊이", 80, 400, 200)
tw = g.S("tw", "트랜섬 높이", 40, 200, 80); sp = g.S("sp", "스팬드럴 높이", 600, 2000, 1200); gt = g.S("gt", "유리 두께", 10, 60, 28)
cw = g.S("cw", "외부 캡 폭", 30, 200, 60); fd = g.S("fd", "외부 캡 돌출", 20, 600, 150); sBd = g.S("sBd", "패널 하단(층 바닥 아래)", 0, 1500, 700)
p03 = g.P("p03", "0.3"); tgPv = g.T("tgPv", "유리 미리보기", False)

# ---------------- 2. 비틀림·층 ----------------
g.group("g2", "2. 비틀림 규칙과 층 작업면", "높이 1mm당 회전량 = 총 비틀림 ÷ 건물 높이. 층마다(지붕 포함) 작업면을 올리고 그 높이만큼 돌려요.")
rd = g.N("rd", "Maths/Trig/Radians", {"Degrees": sT}, out="Radians")
htot = g.op("htot", MUL, sN, sH, "건물 높이"); fac = g.op("fac", DIV, rd, htot, "mm당 회전")
xy0 = g.N("xy0", XY, {}, "월드 XY", out="Plane")
fc = g.op("fc", ADD, sN, p1, "층수+지붕")
fz = g.N("fz", SER, {"Step": sH, "Count": fc}, "층 높이들", out="Series")
fpt = g.N("fpt", CPT, {"Z coordinate": fz}, out="Point"); fpl = g.N("fpl", XY, {"Origin": fpt}, "층 작업면", out="Plane")
fan = g.op("fan", MUL, fz, fac, "층 회전각")
frot = g.N("frot", ROT, {"Geometry": fpl, "Angle": fan}, "돌린 작업면", out="Geometry")
rCw = g.op("rCw", MUL, sS, pR, "외피 반지름")
cwl = g.N("cwl", POLY, {"Plane": frot, "Radius": rCw, "Segments": p4}, "외피(유리) 선", out="Polygon")
sIn2 = g.op("sIn2", MUL, sIn, p2); sSl = g.op("sSl", SUB, sS, sIn2, "슬래브 한 변"); rSl = g.op("rSl", MUL, sSl, pR)
fpoly = g.N("fpoly", POLY, {"Plane": frot, "Radius": rSl, "Segments": p4}, "슬래브 끝 선", out="Polygon")
cIn2 = g.op("cIn2", MUL, cIn, p2); sDg = g.op("sDg", SUB, sS, cIn2, "구조 한 변"); rDg = g.op("rDg", MUL, sDg, pR, "구조 반지름")
rCore = g.op("rCore", MUL, sC, pR, "코어 반지름")
cpoly = g.N("cpoly", POLY, {"Plane": fpl, "Radius": rCore, "Segments": p4}, "코어 선", out="Polygon")

# ---------------- 3. 슬래브·코어 ----------------
g.group("g3", "3. 슬래브·코어 (콘크리트)", "슬래브는 층 높이(마감 바닥)에서 아래로 두께만큼, 코어를 비우고 만들어요. 코어는 속 빈 튜브로 지붕까지 세워요.")
mg = g.N("mg", MRG, {"Data 1": graft(fpoly), "Data 2": graft(cpoly)}, "층별 묶음", out="Result")
bs = g.N("bs", "Surface/Freeform/Boundary Surfaces", {"Edges": mg}, out="Surfaces")
nT2 = neg("nT2", sT2, "-슬래브 두께")
uzS = g.N("uzS", UZ, {"Factor": nT2}, "아래로", out="Unit vector")
g.N("slab", EXT, {"Base": bs, "Direction": uzS}, "슬래브", True, "concrete")
cp0 = g.N("cp0", POLY, {"Radius": rCore, "Segments": p4}, "코어 바깥", out="Polygon")
ct2 = g.op("ct2", MUL, sCt, p2); cin = g.op("cin", SUB, sC, ct2, "코어 안 한 변"); rCin = g.op("rCin", MUL, cin, pR)
cpI = g.N("cpI", POLY, {"Radius": rCin, "Segments": p4}, "코어 안쪽", out="Polygon")
mg3 = g.N("mg3", MRG, {"Data 1": cp0, "Data 2": cpI}, out="Result")
bs3 = g.N("bs3", "Surface/Freeform/Boundary Surfaces", {"Edges": mg3}, out="Surfaces")
uzC = g.N("uzC", UZ, {"Factor": htot}, out="Unit vector")
g.N("core", EXT, {"Base": bs3, "Direction": uzC}, "코어 벽", True, "concrete")

# ---------------- 4. H형강 단면 ----------------
g.group("g4", "4. H형강 단면 (원점)", "플랜지 2장 + 웨브 1장 사각형을 하나의 H 윤곽으로 합쳐요. 춤 방향이 X축이에요.")
hd = half("hd", dD, "춤/2"); hb = half("hb", dB, "폭/2"); htw = half("htw", dTw, "웨브/2")
xf = g.op("xf", SUB, hd, dTf, "플랜지 안쪽"); tfh = half("tfh", dTf); xw = g.op("xw", SUB, hd, tfh, "웨브 끝")
nhd = neg("nhd", hd); nhb = neg("nhb", hb); nxf = neg("nxf", xf); nxw = neg("nxw", xw); nhtw = neg("nhtw", htw)
dF1 = g.N("dF1", DOM, {"Domain start": xf, "Domain end": hd}, out="Domain"); dFy = g.N("dFy", DOM, {"Domain start": nhb, "Domain end": hb}, out="Domain")
dF2 = g.N("dF2", DOM, {"Domain start": nhd, "Domain end": nxf}, out="Domain")
dWx = g.N("dWx", DOM, {"Domain start": nxw, "Domain end": xw}, out="Domain"); dWy = g.N("dWy", DOM, {"Domain start": nhtw, "Domain end": htw}, out="Domain")
rF1 = g.N("rF1", RECT, {"X Size": dF1, "Y Size": dFy}, "플랜지 1", out="Rectangle"); rF2 = g.N("rF2", RECT, {"X Size": dF2, "Y Size": dFy}, "플랜지 2", out="Rectangle")
rW = g.N("rW", RECT, {"X Size": dWx, "Y Size": dWy}, "웨브", out="Rectangle")
m1 = g.N("m1", MRG, {"Data 1": rF1, "Data 2": rF2}, out="Result"); m2 = g.N("m2", MRG, {"Data 1": m1, "Data 2": rW}, out="Result")
prof = g.N("prof", "Intersect/Shape/Region Union", {"Curves": m2}, "H 윤곽", out="Result")
nr = half("nr", nD, "노드 반지름"); clr = g.op("clr", ADD, nr, tp, "끝 여유(노드+플레이트)")
rDp = g.op("rDp", MUL, dD, kR, "링 보 춤"); rDh = half("rDh", rDp)

# ---------------- 5. 링·절점 ----------------
g.group("g5", "5. 링·절점", "모듈 층마다 구조 링을 슬래브 밑(링 보 중심 높이)에 두고, 링마다 반 칸씩 엇갈린 절점을 찍어요.")
mh = g.op("mh", MUL, sM, sH, "링 간격"); rc1 = g.op("rc1", DIV, sN, sM); rc = g.op("rc", ADD, rc1, p1, "링 개수")
rz = g.N("rz", SER, {"Step": mh, "Count": rc}, "링 층 높이들", out="Series")
drop = g.op("drop", ADD, sT2, rDh, "슬래브 밑까지"); ndrop = neg("ndrop", drop)
rzz = g.op("rzz", ADD, rz, ndrop, "링 보 중심 높이")
rpt = g.N("rpt", CPT, {"Z coordinate": rzz}, out="Point"); rpl = g.N("rpl", XY, {"Origin": rpt}, out="Plane")
ran = g.op("ran", MUL, rz, fac, "링 회전각(그 층과 같게)")
rrot = g.N("rrot", ROT, {"Geometry": rpl, "Angle": ran}, out="Geometry")
rpoly = g.N("rpoly", POLY, {"Plane": rrot, "Radius": rDg, "Segments": p4}, "구조 링", out="Polygon")
nd = g.op("nd", MUL, sD, p4, "링당 절점 수")
jj = g.N("jj", SER, {"Count": nd}, "절점 순번", out="Series")
kk = g.N("kk", SER, {"Count": rc}, "링 번호", out="Series")
kh = g.op("kh", DIV, kk, p2, "반 칸 밀기")
jk = g.N("jk", "Maths/Operators/Addition", {"A": jj, "B": graft(kh)}, "밀린 순번", out="Result")
tn = g.op("tn", DIV, jk, nd, "0~1 위치"); tm = g.op("tm", "Modulus", tn, p1, "한 바퀴 정리")
ev = g.N("ev", EVL, {"Curve": graft(rpoly), "Length": tm, "Normalized": tog}, "절점")
evP = (ev, "Point"); evT = (ev, "Parameter")

# ---------------- 6. 대각재 축선 ----------------
g.group("g6", "6. 대각재 축선", "절점을 두 방향 나선으로 이은 뒤 절점 사이마다 끊어 부재 축선을 얻어요.")
fl1 = g.N("fl1", "Sets/Tree/Flip Matrix", {"Data": evP}, "순번별 세로줄", out="Data")
pl1 = g.N("pl1", "Curve/Spline/PolyLine", {"Vertices": fl1}, "오른 나선", out="Polyline")
ex1 = g.N("ex1", "Curve/Util/Explode", {"Curve": pl1}, out="Segments")
kneg = neg("kneg", kk, "-링 번호")
sh = g.N("sh", "Sets/List/Shift List", {"List": evP, "Shift": graft(kneg)}, "링마다 거꾸로 밀기", out="List")
fl2 = g.N("fl2", "Sets/Tree/Flip Matrix", {"Data": sh}, out="Data")
pl2 = g.N("pl2", "Curve/Spline/PolyLine", {"Vertices": fl2}, "왼 나선", out="Polyline")
ex2 = g.N("ex2", "Curve/Util/Explode", {"Curve": pl2}, out="Segments")
segD = g.N("segD", MRG, {"Data 1": ex1, "Data 2": ex2}, "대각재 축선 전부", out="Result")


def radial(px, pt):
    dc = g.N(px + "dc", "Vector/Point/Deconstruct", {"Point": pt})
    return g.N(px + "rv", "Vector/Vector/Vector XYZ", {"X component": (dc, "X component"), "Y component": (dc, "Y component")}, "바깥 방향", out="Vector")


def member(px, seg, direction, profile, name, mat):
    L = g.N(px + "L", "Curve/Analysis/Length", {"Curve": seg}, out="Length")
    Lc = g.op(px + "Lc", SUB, L, clr)
    e1 = g.N(px + "e1", EVL, {"Curve": seg, "Length": clr, "Normalized": tAbs}, "시작(노드+플레이트만큼 안쪽, mm)", out="Point")
    e2 = g.N(px + "e2", EVL, {"Curve": seg, "Length": Lc, "Normalized": tAbs}, "끝(노드+플레이트만큼 안쪽, mm)", out="Point")
    v = g.N(px + "v", "Vector/Vector/Vector 2Pt", {"Point A": e1, "Point B": e2}, "부재 방향", out="Vector")
    pn = g.N(px + "pn", "Vector/Plane/Plane Normal", {"Origin": e1, "Z-Axis": v}, out="Plane")
    d = direction(px, e1) if callable(direction) else direction
    al = g.N(px + "al", "Vector/Plane/Align Plane", {"Plane": pn, "Direction": d}, "춤 방향 맞춤", out="Plane")
    orr = g.N(px + "or", "Transform/Euclidean/Orient", {"Geometry": profile, "Source": xy0, "Target": al}, "단면 옮기기", out="Geometry")
    g.N(px + "ex", EXT, {"Base": orr, "Direction": v}, name, True, mat)
    return e2, v, al, d


g.group("g7", "7. 대각재 (H형강)", "축선 양 끝을 노드 반지름+플레이트 두께만큼 줄이고(mm), 춤이 건물 바깥을 향하게 H 단면을 세워 축선 방향으로 밀어내요.")
e2, v, al, dRad = member("dg_", segD, radial, prof, "대각재 H형강", "steel")

g.group("g8", "8. 링 보 (H형강, 춤 수직)", "링을 절점에서 끊고 작은 H 단면(비율)을 춤이 수직이 되게 놓아요. 윗면이 슬래브 밑면에 닿아요.")
shat = g.N("shat", "Curve/Division/Shatter", {"Curve": graft(rpoly), "Parameters": evT}, "절점에서 끊기", out="Segments")
uzU = g.N("uzU", UZ, {}, "위쪽", out="Unit vector")
profR = g.N("profR", "Transform/Affine/Scale", {"Geometry": prof, "Factor": kR}, "링 보 단면", out="Geometry")
member("rg_", shat, uzU, profR, "링 보 H형강", "steel")

g.group("g9", "9. 바닥 보 (켜기 스위치)", "층마다 구조 선을 나눈 점에서 코어까지 보를 걸어요. 윗면이 슬래브 밑면에 닿아요. 개수가 많아 기본은 꺼져 있어요.")
fbd = g.op("fbd", MUL, dD, kF, "바닥 보 춤"); fbh = half("fbh", fbd)
fdrop = g.op("fdrop", ADD, sT2, fbh); nfdrop = neg("nfdrop", fdrop)
uzF = g.N("uzF", UZ, {"Factor": nfdrop}, "슬래브 밑으로", out="Unit vector")
gate = g.N("gate", "Sets/List/Dispatch", {"List": frot, "Dispatch pattern": tgFl}, "바닥 보 스위치", out="List A")
dgl = g.N("dgl", POLY, {"Plane": gate, "Radius": rDg, "Segments": p4}, "층별 구조 선", out="Polygon")
fcount = g.op("fcount", MUL, fN, p4, "층당 보 수")
fdv = g.N("fdv", "Curve/Division/Divide Curve", {"Curve": graft(dgl), "Count": fcount}, "보 바깥 끝", out="Points")
gate2 = g.N("gate2", "Sets/List/Dispatch", {"List": cpoly, "Dispatch pattern": tgFl}, out="List A")
ccp = g.N("ccp", "Curve/Analysis/Curve Closest Point", {"Point": fdv, "Curve": graft(gate2)}, "코어 쪽 끝", out="Point")
profF = g.N("profF", "Transform/Affine/Scale", {"Geometry": prof, "Factor": kF}, "바닥 보 단면", out="Geometry")
fv = g.N("fv", "Vector/Vector/Vector 2Pt", {"Point A": ccp, "Point B": fdv}, out="Vector")
fbase = g.N("fbase", MOVE, {"Geometry": ccp, "Motion": uzF}, out="Geometry")
fpn = g.N("fpn", "Vector/Plane/Plane Normal", {"Origin": fbase, "Z-Axis": fv}, out="Plane")
fal = g.N("fal", "Vector/Plane/Align Plane", {"Plane": fpn, "Direction": uzU}, out="Plane")
forr = g.N("for", "Transform/Euclidean/Orient", {"Geometry": profF, "Source": xy0, "Target": fal}, out="Geometry")
g.N("fex", EXT, {"Base": forr, "Direction": fv}, "바닥 보 H형강", True, "steel")

# ---------------- 10. 주강 노드 블록 ----------------
g.group("g10", "10. 주강 노드 (블록)", "원점에 원반형 노드(드럼 + 안팎 캡)를 만들고, 절점마다 축이 건물 바깥을 향하게 블록으로 놓아요. 대각재 끝이 드럼 테두리에 닿아요.")
nh2 = half("nh2", nT); nnh = neg("nnh", nh2)
nb = g.N("nb", CPT, {"Z coordinate": nnh}, out="Point"); nbp = g.N("nbp", XY, {"Origin": nb}, out="Plane")
g.N("drum", CYL, {"Base": nbp, "Radius": nr, "Length": nT}, "노드 드럼", mat="steel")
rcap = g.op("rcap", MUL, nr, p115, "캡 반지름")
cz1 = g.op("cz1", SUB, nnh, p60); cpz = g.N("cpz", MRG, {"Data 1": cz1, "Data 2": nh2}, out="Result")
cbp = g.N("cbp", CPT, {"Z coordinate": cpz}, out="Point"); cbl = g.N("cbl", XY, {"Origin": cbp}, out="Plane")
g.N("caps", CYL, {"Base": cbl, "Radius": rcap, "Length": p60}, "노드 캡", mat="steel")
ndir = radial("nd_", evP)
npn = g.N("npn", "Vector/Plane/Plane Normal", {"Origin": evP, "Z-Axis": ndir}, out="Plane")
npl = g.N("npl", "Vector/Plane/Align Plane", {"Plane": npn, "Direction": uzU}, "노드 자리(축=바깥)")
g.blocks.append({"name": "주강 노드", "parts": ["drum", "caps"], "at": "npl"})

# ---------------- 11. 엔드 플레이트 + 볼트 블록 ----------------
g.group("g11", "11. 엔드 플레이트·볼트 (블록)", "원점에 플레이트 한 장과 볼트 10개(몸통·머리·너트)를 만들고, 대각재 양 끝마다 블록으로 놓아요. 플레이트 뒷면이 노드 드럼에 닿아요.")
px = g.op("px", ADD, hd, eB, "플레이트 X/2"); eh = half("eh", eB); py = g.op("py", ADD, hb, eh, "플레이트 Y/2")
npx = neg("npx", px); npy = neg("npy", py); ntp = neg("ntp", tp)
pa = g.N("pa", CPT, {"X coordinate": npx, "Y coordinate": npy, "Z coordinate": ntp}, out="Point")
pb = g.N("pb", CPT, {"X coordinate": px, "Y coordinate": py}, out="Point")
g.N("plate", BOX2, {"Point A": pa, "Point B": pb}, "엔드 플레이트", mat="steel")
xo = g.op("xo", ADD, hd, eh, "플랜지 밖 볼트 X"); nxo = neg("nxo", xo); yb = g.op("yb", MUL, hb, p06); nyb = neg("nyb", yb)
xs1 = g.N("xs1", MRG, {"Data 1": xo, "Data 2": nxo}, out="Result")
ys1a = g.N("ys1a", MRG, {"Data 1": nyb, "Data 2": p0}, out="Result"); ys1 = g.N("ys1", MRG, {"Data 1": ys1a, "Data 2": yb}, out="Result")
bp1 = g.N("bp1", CPT, {"X coordinate": graft(xs1), "Y coordinate": ys1}, "볼트 6개", out="Point")
xi = g.op("xi", MUL, hd, p045, "웨브 옆 볼트 X"); nxi = neg("nxi", xi); yi = g.op("yi", ADD, htw, eh); nyi = neg("nyi", yi)
xs2 = g.N("xs2", MRG, {"Data 1": xi, "Data 2": nxi}, out="Result"); ys2 = g.N("ys2", MRG, {"Data 1": yi, "Data 2": nyi}, out="Result")
bp2 = g.N("bp2", CPT, {"X coordinate": graft(xs2), "Y coordinate": ys2}, "볼트 4개", out="Point")
bpts = g.N("bpts", MRG, {"Data 1": bp1, "Data 2": bp2}, "볼트 자리", out="Result")
br = half("br", bd, "볼트 반지름"); hr = g.op("hr", MUL, bd, p95, "머리 반지름")
sz0 = g.op("sz0", ADD, tp, p30); nsz = neg("nsz", sz0); slen = g.op("slen", ADD, sz0, p30, "볼트 길이")
uzs = g.N("uzs", UZ, {"Factor": nsz}, out="Unit vector")
sbp = g.N("sbp", MOVE, {"Geometry": bpts, "Motion": uzs}, out="Geometry")
sbl = g.N("sbl", XY, {"Origin": sbp}, out="Plane")
g.N("shank", CYL, {"Base": sbl, "Radius": br, "Length": slen}, "볼트 몸통", mat="steel")
hpl = g.N("hpl", XY, {"Origin": bpts}, out="Plane")
hpg = g.N("hpg", POLY, {"Plane": hpl, "Radius": hr, "Segments": p6}, out="Polygon")
uz20 = g.N("uz20", UZ, {"Factor": p20}, out="Unit vector")
g.N("head", EXT, {"Base": hpg, "Direction": uz20}, "볼트 머리", mat="steel")
nz0 = g.op("nz0", ADD, tp, p25); nnz = neg("nnz", nz0)
uzn = g.N("uzn", UZ, {"Factor": nnz}, out="Unit vector")
npg = g.N("npg", MOVE, {"Geometry": hpg, "Motion": uzn}, out="Geometry")
uz25 = g.N("uz25", UZ, {"Factor": p25}, out="Unit vector")
g.N("nut", EXT, {"Base": npg, "Direction": uz25}, "너트", mat="steel")
rv = g.N("rev", "Vector/Vector/Reverse", {"Vector": v}, "반대 방향", out="Vector")
pn2 = g.N("pn2", "Vector/Plane/Plane Normal", {"Origin": e2, "Z-Axis": rv}, out="Plane")
al2 = g.N("al2", "Vector/Plane/Align Plane", {"Plane": pn2, "Direction": dRad}, out="Plane")
g.N("plpl", MRG, {"Data 1": al, "Data 2": al2}, "플레이트 자리(양 끝)")
g.blocks.append({"name": "엔드 플레이트+볼트", "parts": ["plate", "shank", "head", "nut"], "at": "plpl"})

# ---------------- 12. 커튼월 패널 자리 ----------------
g.group("g12", "12. 커튼월 패널 자리", "층마다 돌린 외피 선을 4변으로 나누고 각 변을 패널 수로 나눠, 패널 왼쪽 아래마다 작업면(X=변 방향, Y=위, Z=바깥)을 세워요. 각 변 시작점에는 코너 기둥 자리도 만들어요.")
edges = g.N("edges", "Curve/Util/Explode", {"Curve": cwl}, "변 4개", out="Segments")
stp = g.op("stp", DIV, p1, nP, "1/패널 수")
tq = g.N("tq", SER, {"Step": stp, "Count": nP}, "0~1 위치", out="Series")
cev = g.N("cev", EVL, {"Curve": graft(edges), "Length": tq, "Normalized": tog}, "패널 모서리")
nb2 = neg("nb2", sBd); uzb = g.N("uzb", UZ, {"Factor": nb2}, out="Unit vector")
pbt = g.N("pbt", MOVE, {"Geometry": (cev, "Point"), "Motion": uzb}, "패널 하단", out="Geometry")
ppl = g.N("ppl", "Vector/Plane/Construct Plane", {"Origin": pbt, "X-Axis": (cev, "Tangent"), "Y-Axis": uzU}, "패널 작업면")
kev = g.N("kev", EVL, {"Curve": edges, "Length": p0, "Normalized": tog}, "변 시작점")
kbt = g.N("kbt", MOVE, {"Geometry": (kev, "Point"), "Motion": uzb}, out="Geometry")
kpl = g.N("kpl", "Vector/Plane/Construct Plane", {"Origin": kbt, "X-Axis": (kev, "Tangent"), "Y-Axis": uzU}, "코너 작업면")

# ---------------- 13. 유닛 패널 원형 ----------------
g.group("g13", "13. 유닛 패널 원형 (원점, Y=위, Z=바깥)", "패널 한 장: 좌우 반쪽 멀리언, 위·중간·아래 트랜섬, 스팬드럴 판(슬래브·링 보를 가림), 복층 유리, 바깥 캡. 모서리용 코너 기둥도 함께 짜요.")
w = g.op("w", DIV, sS, nP, "패널 폭"); mhh = g.op("mhh", DIV, mw, p2, "반쪽 멀리언"); wm = g.op("wm", SUB, w, mhh, "폭-반쪽")
mt = g.op("mt", MUL, md, p06, "트랜섬 깊이"); gz = g.op("gz", MUL, md, p03, "유리 위치"); gz2 = g.op("gz2", ADD, gz, gt)
twh = g.op("twh", DIV, tw, p2); htw2 = g.op("htw2", SUB, sH, tw, "위 트랜섬 밑"); s1 = g.op("s1", SUB, sp, twh); s2 = g.op("s2", ADD, sp, twh)
cwh = g.op("cwh", DIV, cw, p2); ncwh = neg("ncwh", cwh); fz2 = g.op("fz2", ADD, md, fd, "캡 끝")


def box(i, nick, mat, a, b):
    A = g.N(i + "A", CPT, {k: v for k, v in zip(["X coordinate", "Y coordinate", "Z coordinate"], a) if v is not None}, out="Point")
    Bp = g.N(i + "B", CPT, {k: v for k, v in zip(["X coordinate", "Y coordinate", "Z coordinate"], b) if v is not None}, out="Point")
    g.N(i, BOX2, {"Point A": A, "Point B": Bp}, nick, mat=mat); return i


parts = [
    box("mL", "왼쪽 멀리언", "aluminum", (None, None, None), (mhh, sH, md)),
    box("mR", "오른쪽 멀리언", "aluminum", (wm, None, None), (w, sH, md)),
    box("tB", "아래 트랜섬", "aluminum", (mhh, None, None), (wm, tw, mt)),
    box("tT", "위 트랜섬", "aluminum", (mhh, htw2, None), (wm, sH, mt)),
    box("tM", "중간 트랜섬", "aluminum", (mhh, s1, None), (wm, s2, mt)),
    box("spd", "스팬드럴 판", "spandrel", (mhh, tw, gz), (wm, s1, gz2)),
    box("gls", "복층 유리", "glass", (mhh, s2, gz), (wm, htw2, gz2)),
    box("cap", "외부 캡", "aluminum", (ncwh, None, md), (cwh, sH, fz2)),
]
g.blocks.append({"name": "커튼월 유닛", "parts": parts, "at": "ppl"})
nmd = neg("nmd", md)
kparts = [box("kpost", "코너 기둥", "aluminum", (nmd, None, None), (None, sH, md))]
g.blocks.append({"name": "커튼월 코너", "parts": kparts, "at": "kpl"})

g.group("g14", "14. 미리보기 (선택)", "그래스호퍼 화면에서 유리만 실제 자리에 띄워 봐요. Bake에는 영향이 없어요.")
gate3 = g.N("gate3", "Sets/List/Dispatch", {"List": (ppl, "Plane"), "Dispatch pattern": tgPv}, out="List A")
g.N("pv", "Transform/Euclidean/Orient", {"Geometry": ("gls", "Box"), "Source": xy0, "Target": gate3}, "유리 미리보기")
g.nodes[-1]["preview"] = True
for n in g.nodes:
    if n["id"] in ("ppl", "kpl"): n["component"] = "Vector/Plane/Construct Plane"

g.dump("../08_비틀린다이아그리드타워_v3.json", "50층 비틀린 다이아그리드 타워 v3 — 구조 + 유닛 커튼월",
       "층마다 일정하게 돌아가는 정사각형 평면 위에, 바깥 유리 선 → 슬래브 끝 → 다이아그리드 중심선 순서로 안쪽으로 들어가며 켜를 나눴어요. "
       "구조는 모듈 층마다 놓인 링의 절점을 두 방향 나선으로 이은 H형강 대각재, 링 보, 원반형 주강 노드, 엔드 플레이트와 볼트로 이뤄져요. "
       "슬래브는 층 높이에서 아래로, 링 보·바닥 보는 그 밑에 매달려요. 외피는 층마다 돌린 선을 따라 같은 크기의 유닛 패널(멀리언·트랜섬·스팬드럴·유리·캡)이 블록으로 놓이고, 모서리는 코너 기둥으로 마감해요.",
       "Bake하면 노드·엔드 플레이트·커튼월 유닛·코너가 블록으로 들어가요. 바닥 보는 '바닥 보 켜기'로 켜세요. "
       "구조가 유리에 닿으면 '유리 → 다이아그리드 중심 거리'를 늘리세요(대각재 춤/2 + 노드 반지름보다 커야 해요).")
print(len(g.nodes), len(g.wires))
