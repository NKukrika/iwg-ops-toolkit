"""Score the CURRENT pipeline against every human-graded row in a scorecard.

    python score_against_scorecard.py "<path to scorecard.xlsx>"

The scorecard's own `AI ·` columns record what the pipeline said on the day. This
re-runs today's code over the same tickets instead, so the report is about the
code as it stands rather than a history of fixed bugs.

Ticket text is recovered from the daily exports in `for triage/` and, failing
that, the benchmark export. A graded row whose text cannot be found is reported
as uncovered rather than counted -- silently dropping it would flatter the score.
"""
import glob, os, sys, warnings, collections
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, "reference")
import classify as C

SC = sys.argv[1] if len(sys.argv) > 1 else None
if not SC:
    sys.exit("usage: python score_against_scorecard.py <scorecard.xlsx>")


def clean(v):
    s = str(v).strip()
    if s.lower() in ("nan", "none"):
        return ""
    s = s.strip("[]").strip()
    # The pipeline writes UNCATEGORISED, the reviewers write Unclassified. They
    # are the same verdict, and counting them as a miss overstates the error
    # rate -- it did, by two rows, on the first run of this script.
    return "UNCATEGORISED" if s.lower() in ("unclassified", "uncategorised") else s


# ---- ticket text, exports first (they are what the run actually saw)
rows = {}
for f in sorted(glob.glob("for triage/*.xlsx")):
    try:
        d = pd.read_excel(f, sheet_name=0)
    except Exception:
        continue
    if "Number" not in d.columns:
        continue
    for _, r in d.iterrows():
        rows.setdefault(str(r["Number"]).strip(), r)
_from_exports = len(rows)
for f in glob.glob("reference/truth/*training*.xlsx"):
    try:
        d = pd.read_excel(f, sheet_name=0)
    except Exception:
        continue
    for _, r in d.iterrows():
        rows.setdefault(str(r["Number"]).strip(), r)

raw = pd.read_excel(SC, sheet_name="Evaluation Log", header=None)
hdr = [str(v) for v in raw.iloc[2].tolist()]
sc = raw.iloc[3:].copy()
sc.columns = hdr
sc = sc[sc["Incident ID"].astype(str).str.startswith("INC0")]
sc = sc[sc["Incident ID"] != "INC0000001"]

cats, masters, kbas = C.load_reference()
kidx, midx = C.build_kba_index(kbas), C.build_master_index(masters)
L = C.load_learned_groups()
groups, signals = C.load_groups()

stat = {k: [0, 0] for k in ("category", "routing", "priority")}
missed = collections.Counter()
pairs = collections.Counter()
uncovered = []
detail = []

for _, r in sc.iterrows():
    tid = clean(r["Incident ID"])
    src = rows.get(tid)
    if src is None:
        uncovered.append(tid)
        continue
    t = C.triage_row(src["Short description"], src.get("Description"),
                     cats, masters, kbas, kidx, midx)
    got_cat = "UNCATEGORISED" if t["category"] == "Unclassified" else t["category"]

    hc = clean(r.get("Human · Category"))
    if hc:
        stat["category"][1] += 1
        if got_cat == hc:
            stat["category"][0] += 1
        else:
            missed[f"category: {got_cat} -> {hc}"] += 1
            pairs[(got_cat, hc)] += 1
            detail.append((tid, "category", got_cat, hc,
                           str(src["Short description"])[:70].replace("\n", " ")))

    hr = clean(r.get("Human · Assignment"))
    gcol = C.find_group_column(src.index)
    if hr and gcol is not None:
        g = C.final_group(src.get(gcol), t["category"], src["Short description"],
                          src.get("Description"), L, groups, signals)["group"]
        stat["routing"][1] += 1
        if C.canon_group(g)[0] == C.canon_group(hr)[0]:
            stat["routing"][0] += 1
        else:
            missed[f"routing: {g} -> {hr}"] += 1
            detail.append((tid, "routing", g, hr,
                           str(src["Short description"])[:70].replace("\n", " ")))

print(f"scorecard        : {os.path.basename(SC)}")
print(f"graded rows      : {len(sc)}")
print(f"text recovered   : {len(sc) - len(uncovered)}  ({_from_exports} tickets in for triage/)")
print(f"uncovered        : {len(uncovered)}")
print()
for k, (ok, tot) in stat.items():
    if tot:
        print(f"  {k:<10} {ok}/{tot} = {100*ok/tot:.1f}%")
print()
print("most common misses:")
for m, n in missed.most_common(15):
    print(f"  {n:>3}  {m}")

if os.environ.get("SHOW_DETAIL"):
    print("\ndetail:")
    for row in detail:
        print("  %-12s %-9s got=%-26s want=%-26s %s" % row)
