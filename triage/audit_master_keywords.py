"""Find master keywords that fire on tickets belonging to a different master.

Run from triage/.

For each keyword, count benchmark tickets containing it and how many of those
carry that master's own MST tag. A keyword appearing on many tickets while
almost never coinciding with its own master is a false-positive generator --
`callstream`, `blocked in myregus` and `linked account` were all found this way
after they had already mis-triaged a live ticket.

Only MST-tagged rows can be judged, so a keyword is reported as UNSUPPORTED
rather than wrong when it never lands on a tagged row: the benchmark cannot
convict it, only fail to defend it.
"""
import csv, sys, warnings
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, "reference")

MIN_HITS = 8          # ignore rare keywords; they cannot do much damage
STOP_AT = 0.15        # flag when under this share of hits carry the MST tag

d = pd.read_excel("reference/truth/training 2.xlsx", sheet_name="Page 1")
text = (d["Short description"].astype(str) + " " + d["Description"].astype(str)).str.lower().tolist()
tags = [str(v) if v == v else "" for v in d["Tags"].tolist()]

masters = list(csv.DictReader(open("reference/master-tickets.csv", encoding="utf-8")))

rows = []
for m in masters:
    mst = (m.get("MST Tag") or "").strip().replace(" ", "")
    # A master with no MST tag can never coincide with one, so every keyword on
    # it would score 0% and read as damning when the benchmark simply cannot
    # judge it. [SOA] Balance Mismatch is exactly that case, and its keywords
    # dominated the first run of this audit for no reason.
    if not mst:
        continue
    for kw in [k.strip().lower() for k in m["Symptom keywords"].split(";") if k.strip()]:
        hits = [i for i, s in enumerate(text) if kw in s]
        if len(hits) < MIN_HITS:
            continue
        own = sum(1 for i in hits if mst and mst in tags[i].replace(" ", ""))
        rows.append({
            "master": m["Master Name"], "mst": mst or "(none)", "kw": kw,
            "hits": len(hits), "own": own,
            "share": own / len(hits) if hits else 0.0,
        })

rows.sort(key=lambda r: (r["share"], -r["hits"]))
print(f"{'KEYWORD':<38} {'HITS':>5} {'OWN MST':>8} {'SHARE':>7}  MASTER")
print("-" * 118)
shown = 0
for r in rows:
    if r["share"] >= STOP_AT:
        continue
    verdict = "UNSUPPORTED" if r["own"] == 0 else ""
    print(f"{r['kw'][:38]:<38} {r['hits']:>5} {r['own']:>8} {r['share']*100:>6.1f}%  "
          f"{r['master'][:44]} {verdict}")
    shown += 1
print(f"\n{shown} keyword(s) fire on {MIN_HITS}+ benchmark tickets while under "
      f"{int(STOP_AT*100)}% carry their own master's MST tag.")
print("Judge each on the wording: a keyword that names a SYMPTOM is fine even when "
      "untagged rows dominate;\none that names a tool, a place or a noun the ticket "
      "merely mentions is the dangerous shape.")
