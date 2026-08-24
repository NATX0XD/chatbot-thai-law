# -*- coding: utf-8 -*-
"""Grid-search the fusion weights against probes with a known correct act+section.

Records how settings.weight_dense / weight_bm25 / guarantee_top were chosen.
Re-run after changing the embedding model or the corpus:

    python -m ingest.tune_fusion

Reported metrics: act@1 / act@3 = the governing act appears at rank 1 / within
top 3. sec@1 / sec@6 = the exact section that answers the question.
"""
import itertools
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from app.config import settings
from app.query_expand import expand
from app.retriever import Retriever, SECTION_Q_RE, THAI_DIGITS

R = Retriever()

# (question, act substring, section that actually answers it or None)
PROBES = [
    ("เจ้าหนี้ทวงหนี้ตี 1 ผิดไหม", "ทวงถามหนี้", "9"),
    ("เจ้าหนี้โทรทวงหนี้ตอนตี 1 ผิดกฎหมายไหม", "ทวงถามหนี้", "9"),
    ("ทวงหนี้ตอนดึกได้ไหม", "ทวงถามหนี้", "9"),
    ("โดนไล่ออก ได้เงินไหม", "คุ้มครองแรงงาน", "118"),
    ("ถูกเลิกจ้างกะทันหัน ได้ค่าชดเชยเท่าไหร่", "คุ้มครองแรงงาน", "118"),
    ("ลาพักร้อนกี่วัน", "คุ้มครองแรงงาน", "30"),
    ("ลาคลอดได้กี่วัน", "คุ้มครองแรงงาน", "41"),
    ("นายจ้างหักเงินเดือนได้ไหม", "คุ้มครองแรงงาน", "76"),
    ("ทำโอทีได้เงินเท่าไหร่", "คุ้มครองแรงงาน", None),
    ("บริษัทเก็บข้อมูลส่วนตัวต้องขอความยินยอมไหม", "ข้อมูลส่วนบุคคล", None),
    ("ขอลบข้อมูลส่วนตัวได้ไหม", "ข้อมูลส่วนบุคคล", None),
    ("คุ้มครองแรงงาน มาตรา 118", "คุ้มครองแรงงาน", "118"),
]

def run(w_dense, w_bm25, g_dense, g_bm25, top_k=6):
    act1 = sec1 = act3 = sec6 = 0
    for q, act, sec in PROBES:
        query, _ = expand(q.translate(THAI_DIGITS))
        dense, dscore = R._dense(query, settings.top_k_dense)
        sparse, bscore = R._sparse(query, settings.top_k_bm25)
        fused = {}
        for ranking, w in ((dense, w_dense), (sparse, w_bm25)):
            for rank, idx in enumerate(ranking):
                idx = int(idx)
                fused[idx] = fused.get(idx, 0.0) + w / (settings.rrf_k + rank + 1)
        wanted = set(SECTION_Q_RE.findall(query))
        for idx in list(fused):
            if wanted and R.corpus[idx]["section"] in wanted:
                fused[idx] += 0.5
        sel = []
        for idx in [int(i) for i in dense[:g_dense]] + [int(i) for i in sparse[:g_bm25]]:
            if idx not in sel: sel.append(idx)
        for idx in sorted(fused, key=lambda i: -fused[i]):
            if len(sel) >= top_k: break
            if idx not in sel: sel.append(idx)
        order = sorted(sel[:top_k], key=lambda i: -fused[i])
        recs = [R.corpus[i] for i in order]
        if recs and act in recs[0]["act"]: act1 += 1
        if any(act in r["act"] for r in recs[:3]): act3 += 1
        if sec:
            if recs and act in recs[0]["act"] and recs[0]["section"] == sec: sec1 += 1
            if any(act in r["act"] and r["section"] == sec for r in recs): sec6 += 1
    n, ns = len(PROBES), sum(1 for _,_,s in PROBES if s)
    return act1, act3, sec1, sec6, n, ns

print(f"{'w_dense':>7} {'w_bm25':>6} {'gD':>3} {'gB':>3} | {'act@1':>6} {'act@3':>6} {'sec@1':>6} {'sec@6':>6}")
best = None
for wd, wb, gd, gb in itertools.product([1.0, 1.5, 2.0, 3.0], [0.3, 0.5, 1.0], [1, 2, 3], [0, 1, 2]):
    a1, a3, s1, s6, n, ns = run(wd, wb, gd, gb)
    score = (a1 + a3 + s1 + s6)
    if best is None or score > best[0]: best = (score, wd, wb, gd, gb, a1, a3, s1, s6)
    if (wd, wb) in [(1.0,1.0),(2.0,0.5),(3.0,0.5)] and gb in (0,2):
        print(f"{wd:>7} {wb:>6} {gd:>3} {gb:>3} | {a1:>3}/{n:<2} {a3:>3}/{n:<2} {s1:>3}/{ns:<2} {s6:>3}/{ns:<2}")
print()
print("BEST:", f"w_dense={best[1]} w_bm25={best[2]} guarantee_dense={best[3]} guarantee_bm25={best[4]}",
      f"-> act@1 {best[5]}/{len(PROBES)}  act@3 {best[6]}/{len(PROBES)}  sec@1 {best[7]}  sec@6 {best[8]}")
a1,a3,s1,s6,n,ns = run(1.0,1.0,2,2)
print("CURRENT (w 1:1, guarantee 2/2):", f"act@1 {a1}/{n}  act@3 {a3}/{n}  sec@1 {s1}/{ns}  sec@6 {s6}/{ns}")
