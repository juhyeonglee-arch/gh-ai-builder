# -*- coding: utf-8 -*-
"""PR 댓글 본문 만들기: python tests/pr_report.py <결과폴더> <그림 기본 URL> > body.md"""
import glob, io, os, sys
from urllib.parse import quote

out, base = sys.argv[1], sys.argv[2].rstrip("/")
parts = ["<!-- gh-ai-ci-report -->"]
for f in ("summary.md", "web_summary.md"):
    p = os.path.join(out, f)
    if os.path.exists(p): parts.append(io.open(p, encoding="utf-8").read())
pngs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(out, "*.png")))
main = [p for p in pngs if p.startswith("08_렌더_")] + [p for p in pngs if p.startswith("웹_")]
rest = [p for p in pngs if p not in main]


def grid(names):
    return "\n".join('<a href="%s/%s"><img src="%s/%s" width="240" alt="%s"></a>' % (base, quote(n), base, quote(n), n) for n in names)


if main: parts += ["### 확인 그림 (08 타워 렌더 · 웹 미리보기)", grid(main)]
if rest: parts += ["<details><summary>예제별 간이 그림</summary>\n", grid(rest), "\n</details>"]
sys.stdout.write("\n\n".join(parts) + "\n")
