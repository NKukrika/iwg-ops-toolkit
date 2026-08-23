# IWG Ops Toolkit

Three Claude Code skills for the production monitoring and ticket triage work, plus the triage
reference data they run against.

| Skill | What it does |
|---|---|
| `cp-monitoring` | Six-step Customer Portal / Pantheon production cycle against Azure App Insights |
| `th-monitoring` | Six-step TeamHub production cycle against Azure |
| `ticket-triage-master` | Triages a ServiceNow export against the master-ticket registry, KBAs and routing rules |

**Clone the repo, open it in Claude Code, and all three are available.** They are project
skills, so they activate automatically when you are working inside this folder — there is
nothing to install into Claude Code itself.

> **New to this? Start with [SETUP.md](SETUP.md).** It walks through installing Claude Code,
> Git, Python and the Azure CLI from nothing, and assumes no terminal experience. The section
> below is the short version, for people who already have those tools.

---

## Setup

Work through these once. The whole thing takes about five minutes, and step 3 is the one that
usually needs someone else.

### 1. Clone and open

```
git clone https://github.com/NKukrika/iwg-ops-toolkit.git
cd iwg-ops-toolkit
claude
```

Confirm the skills loaded by typing `/` — you should see `cp-monitoring`, `th-monitoring` and
`ticket-triage-master` in the list.

### 2. Python

Python 3 must be on your PATH:

```
python --version
```

Triage additionally needs two packages (the monitoring skills are standard library only):

```
pip install -r requirements.txt
```

### 3. Azure access — the one that can block you

Both monitoring skills authenticate by shelling out to the Azure CLI. They run as **you**;
no credentials are stored in this repo.

Install the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), then:

```
az login
az account show
```

You need **Reader** on the `APPS_EU_PROD` subscription:

```
a464f508-ff11-423c-bab6-8eadb42ebcf2
```

Verify you can actually reach it:

```
az account get-access-token --resource https://management.azure.com/ --query expiresOn -o tsv
```

If that prints a timestamp, you are good. If it errors, or `az account list` doesn't show
`APPS_EU_PROD`, **request the Reader role assignment from the platform team** — the monitoring
skills cannot work until it lands, and this is the step with a human in the loop, so raise it
first.

### 4. Atlassian (only if you'll publish or file tickets)

Reading Azure needs nothing from Atlassian. You only need access if you will:

- publish monitoring reports to Confluence space `CPW`, or
- file or search Jira tickets during triage or monitoring.

In Claude Code that means authorising the Atlassian connector for your account.

---

## Running things

### Monitoring

Just ask — *"run CP monitoring"* or *"run TeamHub monitoring"* — or invoke `/cp-monitoring` /
`/th-monitoring` directly. Each runs six checks against one pinned time window so every figure
in a report is comparable.

To pin a 24-hour window explicitly:

```
cd .claude/skills/cp-monitoring/tools
python cyclewin.py new --window 24h
python collect.py
```

### Triage

```
cd triage
python run_triage.py "path/to/servicenow-export.xlsx"
```

Output lands in `triage/runs/Triage_<date>.xlsx`. The first sheet, `Finished Triage`, is the
triage as done; the working detail is in the later sheets.

After editing **any** file in `triage/reference/`, run `python measure.py` from `triage/` — it
re-checks accuracy against the benchmark set so a reference edit cannot silently degrade
matching.

---

## Team policy: the Proposed Masters tally

A new master ticket is created only once the same issue has been seen **more than 10 times**.
That running count lives in the `Proposed Masters` sheet **inside the newest workbook in
`triage/runs/`** — deliberately in one place, because two copies of a running count drift apart.

By default `triage/runs/` is gitignored, because those workbooks contain real ServiceNow ticket
data. **That means a fresh clone starts with no tally.**

Decide as a team which you want:

- **Share the tally (recommended if more than one person triages).** Commit the newest workbook
  after each run so the count travels with the repo:
  ```
  git add -f triage/runs/Triage_<date>.xlsx
  git commit -m "triage run <date>"
  ```
  Commit only the newest one — committing all of them puts the full ticket history in git
  permanently.
- **Keep it local.** Leave the ignore rule as is and accept that one nominated person owns the
  tally; everyone else does per-batch triage without cumulative counts.

Whichever you pick, be deliberate about it — this is the one piece of shared state in the repo.

---

## Known defects

Worth knowing before you trust the saved artifacts:

- **`report.py` cannot honour a 24-hour pin.** It re-pins the window itself, so a run can
  silently become a shift window on partial data. Pin with `cyclewin.py new --window 24h` and
  collect with `collect.py` instead.
- **CP `collect.py` step 4 omits Http5xx.** The saved JSON/HTML understate step 4; run
  `healthcheck.py` separately for those figures.
- **`q.py` dies on non-ASCII output** under the Windows console codec. Prefix ad-hoc runs with
  `PYTHONIOENCODING=utf-8`.
- The CP reference table calls the API plan "P1v3 cap 2". It **autoscales** — 2 to 6 instances
  observed. Do not describe it as capped.
- TeamHub's workbook computes `Availability %` independently of the `num_failed_requests`
  column beside it, so the two do not always reconcile. Bands follow availability.
- Triage **root cause is a suggestion**, measured at ~41% with a ceiling near 43% from ticket
  text alone. Confirm before saving.

---

## Layout

```
.claude/skills/
  cp-monitoring/        SKILL.md, reference/, tools/
  th-monitoring/        SKILL.md, reference/, tools/
  ticket-triage-master/ SKILL.md
triage/
  run_triage.py         the runner
  measure.py            accuracy check — run after any reference edit
  reference/            registry, categories, KBA index, routing, priority matrices
  runs/                 output workbooks (gitignored by default)
requirements.txt
```

Runtime state (`window.json`, `run.json`, logs, `__pycache__`) is gitignored. A stale
`window.json` would make a monitoring cycle report on the wrong period, so never commit one.
