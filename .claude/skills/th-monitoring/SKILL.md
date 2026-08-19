---
name: th-monitoring
description: Run the six-step TeamHub production monitoring cycle against Azure (KPI availability, synthetic availability tests, App Service, SQL database, application failures, fired alerts) and record findings in Jira project CEN. Use when asked to run TeamHub or Team Hub monitoring, check TeamHub production health, produce the TeamHub monitoring report, investigate why a TeamHub KPI dropped, or compare TeamHub KPI trends across periods.
---

# TeamHub production monitoring

Six checks against IWG's TeamHub production estate, all reading one pinned window so every
figure in a report is directly comparable.

TeamHub is a **single API tier** (`teamhubapi.iwgplc.com`) plus a mobile client, backed by
**one App Service Plan running one instance** and **one Basic-tier SQL database**. There is
no web tier and no health probe.

**Scope is TeamHub only.** Downstream Proton health is deliberately not measured here — the
Customer Portal cycle owns it, and measuring it twice produces two reports arguing about the
same numbers. TeamHub calls Proton heavily, so a genuine Proton fault will show up as
TeamHub request failures; route it to PAPI when it does.

`SKILL_DIR` means the directory containing this file. Run everything from `SKILL_DIR/tools`.

## Before starting

```bash
az account show --query "{sub:name, user:user.name}" -o json
```

Expect `APPS_EU_PROD`. If not signed in, the user runs `az login`. If this fails, stop.

## Step 0 — pin the window

**Always first.** Every step reads the pin.

```bash
cd <SKILL_DIR>/tools
python cyclewin.py new --window 24h
```

**24h is the standing default.** Do not report other ranges in cycle output or cite them in a
Jira ticket. A longer window may be queried privately to judge whether something is new.

Named shifts exist (`--shift morning|midday|evening`, 10h/7h/7h, Europe/Sarajevo). Use one
only when the user names it.

## Steps 1–6

```bash
python report.py --no-save        # summary to console
python report.py --out <dir>      # ...and save HTML + JSON
python collect.py > run.json      # raw data for analysis
```

| # | Check | Source |
|---|---|---|
| 1 | KPI availability | Workbook `Teamhub` section — **nine KPIs from one query** |
| 2 | Availability tests | 6 synthetic tests, 7 locations |
| 3 | App Service | Plan CPU/memory + site 5xx, response time, working set |
| 4 | SQL database | DTU, storage, sessions, failed connections, deadlocks |
| 5 | Application failures | TeamHub's own failing endpoints and exceptions, API + mobile |
| 6 | Alerts | Both components |

Ad-hoc KQL:

```bash
python q.py --app we-teamhub-prod-insights-1 --query "<KQL>"
python q.py --app Teamhub-Mobile-Prod --window 4h --file x.kql
```

### Step 1 returns nine KPIs from one tile

The workbook computes every TeamHub KPI in a single query returning one row per feature:
Login, Get User Details, Add Service, Edit Service, Create Order, Update Agreement, Booking
Check-in, Booking Check-out, Business engine.

### Step 3 — there is no health probe

`we-teamhub-prod-app-1` has `healthCheckPath: null` and `alwaysOn` false, so **no
`HealthCheckStatus` metric is emitted**. This is **known and accepted — do not report it.**
Step 3 reports the App Service metrics that do exist and says nothing about the missing probe.

### Step 4 — the database is small

`teamhub-api` is **Basic tier, 5 DTU, 2 GB** backing a production API. The bands used
(amber 75%, red 90%) are our own convention rather than Azure config, and the report must say
so — it affects how the numbers should be read. The **absence of alert rules on this database
is known and accepted; do not flag it.**

### Step 5 — rate-based, not count-based

TeamHub traffic swings roughly **20× between weekday and weekend** (staff tool). A fixed
failure count breaches on everything Tuesday and nothing Sunday. Endpoints are flagged at
**≥5% failures over ≥20 calls**; exception types at **≥25 occurrences**. Tune in `estate.py`.

## Report format

**Section 1** lists **every KPI even at 100%**, worst first, with a colour dot and a closing
tally. **Colour appears in section 1 only** — elsewhere use bold on the number that matters.
No "Step" column. No P95 section.

Bands: 🟢 ≥ 99.9% · 🟡 < 99.9% · 🔴 < 99.0% · ⚪ no data

Close with open items and anything flagged to infra.

## Always band on the average, never the maximum

Alert rules evaluate 5-minute **averages**. Banding on the 5-minute **maximum** produces
criticals the configured alerts would never fire. Both are collected: `peak` is the highest
average and is what you band on; `spike` is the highest maximum and is context only.

This matters here in practice — a recent window showed response time spiking to **55.6s**
while the 5-minute average peaked at **0.56s**, and SQL DTU spiking to **77%** while the
average peaked at **2.08%**. Reporting either spike as a breach would be wrong.

## Thresholds

| Signal | Threshold | Source |
|---|---|---|
| Plan CPU | > 90% | Azure alert (Sev2) |
| Plan Memory | > 90% | Azure alert (Sev2) |
| Site Http5xx | > 200 | Azure alert (Sev1) |
| Site response time | > 6s | Azure alert (Sev2) |
| Site working set | > 5 GB | Azure alert (Sev2) |
| AI availability | < 50% | Azure alert (Sev1) |
| SQL DTU / storage / sessions | 75% amber, 90% red | **our convention — no alerts exist** |

KPI log alerts (failure counts): Get User Details > 200/5min (Sev1), Business Engine Lounge
Checkin > 50/30min (Sev1), Business Engine > 0/30min (Sev2).

Say which basis you are quoting — the workbook bands are percentages, the alert rules are
counts.

## Traps

**`success` is a string.** `availabilityResults` uses `"1"`/`"0"`; `requests` and
`dependencies` use `"True"`/`"False"`. `success == false` matches nothing and silently
reports zero failures.

**`az` is a `.cmd` shim on Windows** — an `&` in a URL passed to `az rest` gets eaten by
`cmd.exe`. The bundled scripts call ARM directly with a bearer token.

**The metric dimension is `Instance`, capital I.**

**Low volume inflates percentages.** Several KPIs run at single-digit daily requests (Edit
Service can be 4). One failure moves them a long way. **Always read the request count next to
the percentage and say so in the report.**

## Jira — project CEN

```jql
project = CEN AND issuetype = "Investigation task"
  AND summary ~ "Q3 - TeamHub Availability KPI 2026"
```

with `Dev Investigation of CEN-XXXXX ...` sub-tasks beneath. Read
`reference/jira-process.md`. The rules:

1. **Scan before filing.** Cite an existing active ticket rather than duplicating.
2. **Post as a comment. Never edit a description.**
3. **Only red (<99.0%) gets a dated table row.** Weekly rows are the backbone.
4. **Route by where the failure is** — a Proton fault surfaced by TeamHub goes to PAPI.
5. **Infra/alerting gaps are flag-only.**
6. **Never create an issue without explicit approval.**

Read `reference/known-issues.md` before reporting anything as new.

## Key resources

| | |
|---|---|
| Subscription | `APPS_EU_PROD` / `a464f508-ff11-423c-bab6-8eadb42ebcf2` |
| Resource group | `RG_APPS_TEAMHUB_PROD` |
| App Insights | `we-teamhub-prod-insights-1` (API), `Teamhub-Mobile-Prod` (mobile) |
| Site | `we-teamhub-prod-app-1` — `teamhubapi.iwgplc.com` |
| Plan | `we-teamhub-prod-asp-1` (P1v3, capacity 1) |
| SQL | `we-teamhub-prod-sql-1` / `teamhub-api` (Basic, 5 DTU, 2 GB) |
| Jira | `regusit.atlassian.net` — CEN, MST, PAPI, TTN |

All environment-specific values live in `tools/estate.py`. Change them there, not in query code.
