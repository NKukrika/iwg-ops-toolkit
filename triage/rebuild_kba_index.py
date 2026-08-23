"""Rebuild reference/kba-index.csv from a ServiceNow kb_knowledge export.

    python rebuild_kba_index.py "reference/truth/<export>.xlsx"

Run from the triage/ directory. Defaults to the most recent export path.

The export is a full refresh, not a delta: it contains every KBA already in the
index plus new ones. So this rebuilds rather than merges, but carries forward the
hand-curated columns -- master-ticket mappings, confidence and notes -- by
joining on KB Number. Those are human judgement and nothing else can recreate
them.

Search text follows the existing convention exactly: title, then the article body
with HTML stripped, truncated to 1200 characters. The cap is deliberate --
BENCHMARK records KBA search under-reporting through query dilution, and 126 rows
in the current index sit exactly at 1200.
"""
import csv, re, sys, warnings
import pandas as pd

warnings.filterwarnings("ignore")

SRC = sys.argv[1] if len(sys.argv) > 1 else "reference/truth/kb_knowledge 2.xlsx"
IDX = "reference/kba-index.csv"
CAP = 1200

COLUMNS = ["KB Number", "Title", "Audience", "KB Category (ServiceNow)",
           "Covers master ticket", "Mapping confidence", "Search text", "Notes"]

# Derived from the 396 overlapping rows, where every value mapped to exactly one
# Audience with no ambiguity.
AUDIENCE = {
    "IT L1 Service Desk KB": "L1",
    "IT L2/L3 Technical KB": "L2",
    "Customer Support":      "Customer Support",
    "End-User Support":      "End User",
    "Centre Support":        "Centre Support",
    "Known Errors":          "Known Errors",
}


def strip_html(h):
    """ServiceNow article bodies are raw HTML; the index stores prose."""
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<br\s*/?>", " ", h, flags=re.I)
    h = re.sub(r"</(p|div|li|tr|h[1-6])>", " ", h, flags=re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'"), ("&rsquo;", "'"), ("&ldquo;", '"'),
                 ("&rdquo;", '"'), ("&ndash;", "-"), ("&mdash;", "-")]:
        h = h.replace(a, b)
    return re.sub(r"\s+", " ", h).strip()


def clean(v):
    s = "" if v is None else str(v)
    return "" if s.lower() == "nan" else s.strip()


old = {r["KB Number"].strip(): r
       for r in csv.DictReader(open(IDX, encoding="utf-8"))}
new = pd.read_excel(SRC, sheet_name="Page 1")

rows, unmapped_kb, no_body, carried = [], set(), 0, 0
for _, r in new.iterrows():
    num = clean(r["Number"])
    title = clean(r["Short description"])
    kb = clean(r["Knowledge base"])
    if kb not in AUDIENCE:
        unmapped_kb.add(kb)

    body = clean(r["Article body"])
    if body:
        text = (title + " " + strip_html(body)).strip()
    else:
        no_body += 1
        text = title
    text = re.sub(r"\s+", " ", text)[:CAP].strip()

    prev = old.get(num)
    if prev and clean(prev.get("Covers master ticket")):
        carried += 1

    rows.append({
        "KB Number":                num,
        "Title":                    title,
        "Audience":                 AUDIENCE.get(kb, kb),
        "KB Category (ServiceNow)": clean(r["Category"]),
        "Covers master ticket":     clean(prev.get("Covers master ticket")) if prev else "",
        "Mapping confidence":       clean(prev.get("Mapping confidence")) if prev else "Unmapped",
        "Search text":              text,
        "Notes":                    clean(prev.get("Notes")) if prev else "",
    })

if unmapped_kb:
    sys.exit(f"unknown Knowledge base value(s), refusing to guess: {sorted(unmapped_kb)}")

# A KB Number appearing twice would silently overwrite one article.
seen = [r["KB Number"] for r in rows]
if len(seen) != len(set(seen)):
    sys.exit("duplicate KB Numbers in the export -- resolve before rebuilding")

lost = set(old) - set(seen)
if lost:
    sys.exit(f"{len(lost)} KBAs in the current index are absent from the export "
             f"and would be lost: {sorted(lost)[:5]} ...")

with open(IDX, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=COLUMNS)
    w.writeheader()
    w.writerows(rows)

L = sorted(len(r["Search text"]) for r in rows)
print(f"  wrote {len(rows)} KBAs  ({len(rows) - len(old)} new, {len(old)} refreshed)")
print(f"  curated master mappings carried forward: {carried}")
print(f"  title-only (no article body):            {no_body}")
print(f"  search text: median {L[len(L)//2]}  p90 {L[int(len(L)*.9)]}  max {L[-1]}")
