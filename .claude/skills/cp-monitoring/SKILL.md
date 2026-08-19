---
name: cp-monitoring
description: Run the six-step Customer Portal production monitoring cycle against Azure App Insights (KPI availability, synthetic availability tests, App Service Plan resources, health probes, Proton endpoint failures, fired alerts) and record findings in Jira. Use when asked to run CP monitoring, check Customer Portal or Pantheon production health, produce the monitoring report, investigate why a KPI dropped, or compare KPI trends across periods.
---

# Customer Portal production monitoring

Six checks against IWG's Pantheon production estate, all reading one pinned time window so
every figure in a report is directly comparable.

`SKILL_DIR` below means the directory containing this file. Run everything from
`SKILL_DIR/tools`.

## Before starting

Verify Azure access once per session. If this fails, stop and tell the user — the whole
cycle depends on it.

```bash
az account show --query "{sub:name, user:user.name}" -o json
```

Expect subscription `APPS_EU_PROD`. If not signed in, the user runs `az login`.

## Step 0 — pin the window

**Always do this first.** Every step reads the pin, which is what makes the figures
comparable.

```bash
cd <SKILL_DIR>/tools
python cyclewin.py new --window 24h
```

**24h is the standing default.** Do not report 7-day or other ranges in cycle output, and
never cite them in a Jira ticket. A longer window may be queried privately to judge whether
something is new or chronic — the report states 24h figures only.

Named shifts exist (`--shift morning|midday|evening`, 10h/7h/7h, Europe/Sarajevo). Use one
only when the user names it.

## Steps 1–6 — collect

One command runs all six and prints a summary:

```bash
python report.py --no-save          # summary to console
python report.py --out <dir>        # ...and save HTML + JSON
```

To work with the data directly (for analysis, or to render your own report):

```bash
python collect.py > run.json        # all six steps as one JSON document
```

| # | Check | Source |
|---|---|---|
| 1 | KPI availability | 11 workbook tiles, executed verbatim |
| 2 | Web & API availability | Synthetic tests on both App Insights components |
| 3 | App Service Plan resources | CPU/memory per instance vs Sev1 thresholds |
| 4 | Health check | `HealthCheckStatus` per instance, plus Http5xx |
| 5 | Proton failure scan | Endpoints above 1,500 failures |
| 6 | Alerts | Fired, still firing, unacknowledged |

For ad-hoc KQL against any component:

```bash
python q.py --app <component> --query "<KQL>"      # uses the pinned window
python q.py --app <component> --window 4h --file x.kql   # one-off override
```

## Report format

Fixed with the user. Follow it exactly.

**Section 1 — KPI Availability.** Every KPI listed **even at 100%**, worst first. Columns:
KPI, Availability, Requests, Failed, and a colour dot. Close with a tally line.

Bands (from workbook tile config): 🟢 ≥ 99.9% · 🟡 < 99.9% · 🔴 < 99.0% · ⚪ no data

**Section 2 — Web & API Availability.** Table plus a prose reason for anything below 100%.

**Sections 3–6** — same table style.

**Colour appears in section 1 only.** Everywhere else, emphasis comes from bold on the
number that matters. This was an explicit instruction.

**Do not include:** a "Step" column, or a KPI response-time / P95 section. Both were
explicitly removed.

Close with open items, and anything flagged to infra.

## Threshold bases — say which one you mean

Two independent layers. A KPI can be amber on the dashboard while nothing fires.

| Layer | Basis |
|---|---|
| Workbook RAG bands | Percentage: ≥99.9 / <99.9 / <99.0 |
| Azure alert rules | **Failure counts**, e.g. Login >200/5min (P1), >100/1h (P2) |
| Plan resources | CPU >90%, Memory >80%, both **5-minute average** |

Band plan resources on the highest 5-minute **average**, never the maximum — a momentary
spike inside a bucket is not a threshold breach. The amber band 10 points below each red is
our own convention, not Azure config; label it as such.

## Traps that will silently give wrong answers

**`success` is a string, and its values differ per component.**

```kql
availabilityResults | where tostring(success) == "1"       // "1" / "0"
requests            | where tostring(success) == "True"    // "True" / "False"
```

`success == false` matches **nothing** and reports zero failures. A query written that way
cannot find a failure. Check the type per component first.

**`az` is a `.cmd` shim on Windows** — an `&` in a URL passed to `az rest` gets eaten by
`cmd.exe`. Call ARM and the App Insights API directly with a bearer token from
`az account get-access-token`, as the bundled scripts do.

**The metric dimension is `Instance`, capital I.** A lowercase comparison collapses every
instance into one bucket and hides per-instance problems.

**`--output table` returns empty** for aggregate `az monitor app-insights query` results.
Use JSON.

## Jira

Read `reference/jira-process.md` before touching Jira. The essentials:

1. **Scan before filing — always.** If an active ticket already covers it, cite that ticket
   instead of raising a duplicate.
2. **Post findings as a comment. Never edit a description.**
3. **Only red (<99.0%) gets a dated table row.** Weekly rows are the backbone.
4. **Route by where the failure is** — Proton API failing → PAPI directly.
5. **Infra/alerting coverage gaps are flag-only** — surface them, do not raise tickets.
6. **Never create an issue without explicit approval.** Draft it, present it, wait.

Read `reference/known-issues.md` before reporting any Proton finding — several
high-volume failures are correct-by-design and already owned.

## Analysis beyond one cycle

For trends, comparisons or "why did this drop", `collect.step_kpis(span, start, end, grain)`
accepts any window. The pattern:

```python
import collect
from datetime import datetime, timezone
s = datetime(2026, 6, 1, tzinfo=timezone.utc)
e = datetime(2026, 7, 1, tzinfo=timezone.utc)
kpis = collect.step_kpis(f'{s:%Y-%m-%dT%H:%M:%SZ}/{e:%Y-%m-%dT%H:%M:%SZ}', s, e, '1d')
```

When comparing a partial month to full months, compare **rates and per-day figures**, not
raw totals. When a month looks bad, isolate the worst day and recompute without it — a
single incident can dominate a monthly average and be mistaken for a trend.

## Key resources

| | |
|---|---|
| Subscription | `APPS_EU_PROD` / `a464f508-ff11-423c-bab6-8eadb42ebcf2` |
| Workbook | `02a1d390-302e-4aa1-af96-513237552061` in `rg_apps_ws_prod` |
| CP App Insights | `we-prod-pantheon-appins-api-01`, `-mcp-01`, `we-prod-proton-appins-proton` |
| Web / API components | `we-prod-pantheon-appins-01`, `-api-01` |
| Sites | `we-prod-pantheon-applinux-01`, `-api-01` |
| Plans | `we-prod-pantheon-serplan-01` (P2v3 cap 10), `-api-01` (P1v3 cap 2) |
| Jira | `regusit.atlassian.net` — MST, CP, PAPI, CEN, TTN |
