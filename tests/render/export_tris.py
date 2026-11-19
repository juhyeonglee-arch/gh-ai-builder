"""ghsim 결과 → 재료별 삼각형 바이너리 (three.js 렌더용)."""
import numpy as np, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ghsim as S

def tri_face(f):
    n = len(f)
    if n == 3: return [f]
    if n == 4: return [f[[0, 1, 2]], f[[0, 2, 3]]]
    # 오목 다각형: 귀 자르기
    c = f.mean(0); nrm = np.zeros(3)
    for i in range(n):
        a, b = f[i], f[(i + 1) % n]; nrm += np.cross(a - c, b - c)
    if np.linalg.norm(nrm) < 1e-9: return []
    nrm /= np.linalg.norm(nrm)
    cr = np.einsum("ij,j->i", np.cross(np.roll(f, -1, 0) - f, np.roll(f, -2, 0) - np.roll(f, -1, 0)), nrm)
    if np.all(cr >= -1e-9):  # 볼록 → 부채꼴
        return [f[[0, i, i + 1]] for i in range(1, n - 1)]
    idx = list(range(n)); out = []; guard = 0
    while len(idx) > 3 and guard < 10 * n:
        guard += 1; m = len(idx); cut = False
        for k in range(m):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % m]
            a, b, cc = f[i0], f[i1], f[i2]
            if np.cross(b - a, cc - b) @ nrm <= 1e-9: continue
            ok = True
            for j in idx:
                if j in (i0, i1, i2): continue
                p = f[j]
                if (np.cross(b - a, p - a) @ nrm > 0 and np.cross(cc - b, p - b) @ nrm > 0 and np.cross(a - cc, p - cc) @ nrm > 0):
                    ok = False; break
            if ok:
                out.append(np.array([a, b, cc])); idx.pop(k); cut = True; break
        if not cut: break
    if len(idx) == 3: out.append(f[idx])
    return out

def export(geo, outdir, skip=()):
    os.makedirs(outdir, exist_ok=True)
    buckets = {}
    for x, mat, name in geo:
        if name in skip: continue
        b = buckets.setdefault(mat or "none", {"q": [], "t": [], "o": []})
        for f in S.faces_of(x):
            n = len(f)
            if n == 4: b["q"].append(f)
            elif n == 3: b["t"].append(f)
            else: b["o"].extend(tri_face(f))
    info = {}
    lo = np.full(3, 1e18); hi = -lo
    for m, b in buckets.items():
        parts = []
        if b["q"]:
            q = np.asarray(b["q"], np.float32)
            parts += [q[:, [0, 1, 2]], q[:, [0, 2, 3]]]
        if b["t"]: parts.append(np.asarray(b["t"], np.float32))
        if b["o"]: parts.append(np.asarray(b["o"], np.float32))
        a = np.concatenate(parts).reshape(-1, 9)
        a.tofile(os.path.join(outdir, m + ".bin")); info[m] = int(len(a))
        v = a.reshape(-1, 3); lo = np.minimum(lo, v.min(0)); hi = np.maximum(hi, v.max(0))
    info["_bbox"] = [lo.tolist(), hi.tolist()]
    json.dump(info, open(os.path.join(outdir, "info.json"), "w"))
    return info
