# -*- coding: utf-8 -*-
"""Pick the in-scope thresholds from data instead of guessing them.

Runs two sets of probes through the retriever and reports the score distributions:
questions the corpus should answer, and questions it must refuse -- including the
hard case of legal questions whose law is genuinely missing from the corpus
(tenancy, inheritance, defamation), which a naive threshold happily answers wrong.

    python -m ingest.calibrate
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings  # noqa: E402
from app.coverage import find_gap  # noqa: E402
from app.retriever import Retriever  # noqa: E402

IN_SCOPE = [
    "ถูกเลิกจ้างกะทันหัน ได้ค่าชดเชยเท่าไหร่",
    "ทำงานครบหนึ่งปี ลาพักผ่อนประจำปีได้กี่วัน",
    "นายจ้างหักเงินเดือนได้ไหม",
    "ลาคลอดได้กี่วัน ได้เงินไหม",
    "เจ้าหนี้โทรทวงหนี้ตอนกลางคืนได้ไหม",
    "คนทวงหนี้ไปบอกที่ทำงานว่าเราเป็นหนี้ ผิดไหม",
    "ลูกจ้างประสบอันตรายจากการทำงาน นายจ้างต้องจ่ายอะไรบ้าง",
    "บริษัทเก็บข้อมูลส่วนตัวต้องขอความยินยอมไหม",
    "ขอให้ลบข้อมูลส่วนบุคคลของเราได้ไหม",
    "ซื้อของออนไลน์แล้วของไม่ตรงปก ร้องเรียนที่ไหน",
    "ทำงานล่วงเวลาได้ค่าจ้างเท่าไหร่",
    "นายจ้างไม่จ่ายค่าจ้าง ต้องทำยังไง",
    "ขับรถชนแล้วหนี มีโทษอะไร",
    "ลูกจ้างอายุต่ำกว่า 18 ทำงานอะไรไม่ได้บ้าง",
]

# genuinely not legal questions -- must always refuse
OFF_TOPIC = [
    "สูตรทำต้มยำกุ้งใส่อะไรบ้าง",
    "ทีมไหนชนะฟุตบอลโลกครั้งล่าสุด",
    "ช่วยเขียนโค้ด python อ่านไฟล์ csv หน่อย",
    "พรุ่งนี้ฝนจะตกไหม",
    "แนะนำร้านกาแฟแถวอารีย์",
]

# legal, but the governing law is not in this corpus -- the dangerous middle case
MISSING_LAW = [
    "เจ้าของบ้านยึดเงินมัดจำ ทำอะไรได้บ้าง",
    "พ่อเสียชีวิตไม่ได้ทำพินัยกรรม มรดกแบ่งยังไง",
    "โดนด่าในเฟซบุ๊ก ฟ้องหมิ่นประมาทได้ไหม",
    "จดทะเบียนสมรสแล้วอยากหย่า ต้องทำยังไง",
    "ให้เพื่อนยืมเงินแล้วไม่คืน ฟ้องได้ไหม",
]


def report(name, questions, retriever):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}")
    print(f"{'max_dense':>10} {'max_bm25':>9}  {'top hit':<44} question")
    rows = []
    for q in questions:
        r = retriever.search(q, top_k=1)
        top = r.hits[0].citation if r.hits else "-"
        rows.append((r.max_dense, r.max_bm25))
        print(f"{r.max_dense:>10.4f} {r.max_bm25:>9.2f}  {top[:44]:<44} {q[:40]}")
    dense = sorted(x for x, _ in rows)
    bm25 = sorted(y for _, y in rows)
    print(f"\n  dense  min={dense[0]:.4f}  median={dense[len(dense)//2]:.4f}  max={dense[-1]:.4f}")
    print(f"  bm25   min={bm25[0]:.2f}  median={bm25[len(bm25)//2]:.2f}  max={bm25[-1]:.2f}")
    return rows


def main():
    r = Retriever()
    if r.vectors is None:
        sys.exit("dense index missing -- run: python -m ingest.build_index --dense")

    good = report("IN SCOPE (ต้องตอบได้)", IN_SCOPE, r)
    bad = report("OFF TOPIC (ต้องปฏิเสธ)", OFF_TOPIC, r)
    missing = report("LEGAL BUT LAW MISSING (ต้องปฏิเสธ)", MISSING_LAW, r)

    print(f"\n{'=' * 78}\nTHRESHOLD SEPARATION\n{'=' * 78}")
    lo_good = min(d for d, _ in good)
    hi_off = max(d for d, _ in bad)
    hi_missing = max(d for d, _ in missing)
    print(f"  dense, in-scope vs off-topic : {lo_good:.4f} vs {hi_off:.4f}"
          f"  -> {'separable' if lo_good > hi_off else 'OVERLAP'}")
    if lo_good > hi_off:
        print(f"     suggested MIN_DENSE_SIM = {(lo_good + hi_off) / 2:.3f}"
              f"   (current {settings.min_dense_sim})")
    print(f"  dense, in-scope vs missing-law: {lo_good:.4f} vs {hi_missing:.4f}"
          f"  -> {'separable' if lo_good > hi_missing else 'OVERLAP -- score cannot gate these'}")
    print("     missing-law questions are handled by app/coverage.py, not by a threshold:")
    print("     they retrieve a real, on-topic act that simply does not contain the answer.")
    lo_good_b = min(b for _, b in good)
    hi_bad_b = max(b for _, b in bad + missing)
    print(f"  bm25 , in-scope vs must-refuse: {lo_good_b:.2f} vs {hi_bad_b:.2f}"
          f"  -> {'separable' if lo_good_b > hi_bad_b else 'OVERLAP -- excluded from the gate'}")

    # end-to-end behaviour of both guard layers together
    def passes(questions):
        n = 0
        for q in questions:
            if find_gap(q):          # layer 1: known missing code
                continue
            if r.search(q).in_scope:  # layer 2: cosine gate
                n += 1
        return n

    print(f"\n  both guard layers, MIN_DENSE_SIM={settings.min_dense_sim}:")
    print(f"    in-scope answered   {passes(IN_SCOPE)}/{len(IN_SCOPE)}   (want {len(IN_SCOPE)})")
    print(f"    off-topic leaked    {passes(OFF_TOPIC)}/{len(OFF_TOPIC)}   (want 0)")
    print(f"    missing-law leaked  {passes(MISSING_LAW)}/{len(MISSING_LAW)}   (want 0)")


if __name__ == "__main__":
    main()
