# Setting up, from scratch

For a Windows laptop with none of this installed, and no assumption that you have used a
terminal before. Should take about 40 minutes.

You are not installing three applications. You are installing **Claude Code** — an assistant
that runs in a terminal window — and then downloading this folder, which teaches it three jobs:

| Job | What it does |
|---|---|
| `cp-monitoring` | Six production health checks on Customer Portal / Pantheon |
| `th-monitoring` | Six production health checks on TeamHub |
| `ticket-triage-master` | Sorts a ServiceNow export against the master-ticket registry |

Once set up you run them by asking in plain English — *"run CP monitoring"*. The commands below
are for installing and checking, and you mostly run them once.

**About the terminal.** You will use **PowerShell**, which comes with Windows. Open it by
pressing `Win`, typing `powershell`, and pressing `Enter`. You type a line, press `Enter`, and it
does the thing. If a command prints something unexpected, that is information, not damage —
nothing in step 1 changes anything outside your own user account.

---

## 1. Install four tools

Windows 11 includes `winget`, which installs software from the command line so you do not have
to hunt for download pages. Run these one at a time, waiting for each to finish.

```powershell
# The assistant itself
winget install Anthropic.ClaudeCode

# Downloads this toolkit, and gives Claude a better shell on Windows
winget install Git.Git

# Triage is written in Python
winget install Python.Python.3.13

# How both monitoring skills talk to Azure
winget install Microsoft.AzureCLI
```

Accept any licence agreement that appears. You do not need administrator rights.

> **Now close PowerShell completely and open a new window.**
> Newly installed tools are invisible to a window that was already open. Almost every
> "not recognized" error at this stage is this, and reinstalling does not fix it.

In the new window, check all four arrived. Each should print a version number:

```powershell
claude --version
git --version
python --version
az --version
```

Expect something like `2.1.211 (Claude Code)` and `Python 3.13.x`. If any command says *not
recognized*, open one more fresh window before troubleshooting.

---

## 2. Sign in to Claude

```powershell
claude
```

A browser window opens for you to log in. Claude Code requires a **Pro, Max, Team, Enterprise or
Console** account — the free Claude.ai plan does not include it.

Once you are signed in, type `/exit` to leave. You will come back in step 5.

---

## 3. Get the toolkit

Put it somewhere you can find again. Your user folder is fine.

```powershell
cd $HOME
git clone https://github.com/NKukrika/iwg-ops-toolkit.git
cd iwg-ops-toolkit
```

Install the two Python packages triage needs. The monitoring skills need nothing extra.

```powershell
pip install -r requirements.txt
```

Expect *Successfully installed pandas ... openpyxl ...*, or a note that the requirements are
already satisfied. Either is fine.

> **That `cd iwg-ops-toolkit` matters.** The three skills are attached to this folder, so Claude
> only offers them when you start it from here. Whenever you come back to this work, run
> `cd $HOME/iwg-ops-toolkit` first.

---

## 4. Sign in to Azure

Both monitoring skills read production telemetry as **you** — there are no shared credentials in
this repo.

```powershell
az login
```

A browser opens; sign in with your work account. Then confirm you landed on the right
subscription:

```powershell
az account show --query "{sub:name, user:user.name}" -o json
```

`sub` should read **APPS_EU_PROD**. If it names something else:

```powershell
az account set --subscription APPS_EU_PROD
```

Finally, confirm you can actually reach it — being signed in and having permission are two
different things:

```powershell
az account get-access-token --resource https://management.azure.com/ --query expiresOn -o tsv
```

A timestamp means you are done. If it errors, see the last row of the troubleshooting table.

---

## 5. Connect Atlassian

Only needed to file Jira tickets or publish reports to Confluence. Reading Azure needs nothing
from Atlassian, so you can skip this and come back.

Start Claude from the toolkit folder:

```powershell
cd $HOME/iwg-ops-toolkit
claude
```

Then, inside Claude:

```
/mcp
```

Pick the Atlassian connector and follow the browser prompts. Connectors are per-account, not
per-folder — authorise once and it works everywhere. If `/mcp` ever lists a server as needing
authorisation, this is where you fix it.

---

## 6. Check the three skills work

With Claude running from the toolkit folder, type `/`. You should see `cp-monitoring`,
`th-monitoring` and `ticket-triage-master` in the list.

**If the list is empty, you are in the wrong folder.** Type `/exit`, run
`cd $HOME/iwg-ops-toolkit`, and start `claude` again.

### Monitoring

Just ask:

```
run CP monitoring
```

It pins a time window, runs six checks against Azure and reports back. `run TeamHub monitoring`
does the same for TeamHub. Both stop immediately with a clear message if Azure access is not
working — that is deliberate, not a crash.

### Triage

Triage needs a ServiceNow export. With one saved somewhere:

```powershell
cd triage
python run_triage.py "path\to\your-export.xlsx"
```

The result lands in `triage/runs/Triage_<date>.xlsx`. The first sheet, **Finished Triage**, is
the triage as done; the later sheets hold the working detail.

You are set up when a monitoring run reports real numbers and a triage run produces a workbook.
Neither needs the other — if Azure is still pending, triage works on its own today.

---

## 7. Two things a fresh clone does not have

Both hold real customer ticket data, so neither is in the repository. Triage runs without them;
these are what make it accurate and cumulative. Ask a colleague who already runs triage.

**The benchmark data.** After changing anything in `triage/reference/`, you run
`python measure.py` from `triage/` to confirm you have not made matching worse. That check needs
ground-truth workbooks which are not distributed here. Until they are in place the check cannot
run — so never report a reference change as verified if `measure.py` did not actually run.

**The Proposed Masters tally.** A new master ticket is created only once the same issue has been
seen more than ten times. That running count lives inside a run workbook in `triage/runs/`, which
is gitignored — so a fresh clone starts at zero. If more than one person triages, the team needs
to agree whether to commit the newest workbook after each run or nominate one owner. Ask which is
in force before your first run: running against a stale count silently under-reports every
cluster, and looks like normal output.

---

## When something breaks

| What you see | What it means | Fix |
|---|---|---|
| `'claude' is not recognized` (or git, python, az) | PowerShell was open before the install finished | Close the window completely, open a new one |
| Typing `/` shows no IWG skills | Claude started outside the toolkit folder | `/exit`, then `cd $HOME/iwg-ops-toolkit` and start again |
| `ModuleNotFoundError: pandas` | Python packages did not install | From the toolkit folder, `pip install -r requirements.txt` |
| `az account show` names another subscription | Signed in, but pointed elsewhere | `az account set --subscription APPS_EU_PROD` |
| `The token '&&' is not a valid statement separator` | A CMD command run in PowerShell | Run the lines one at a time |
| Garbled characters from an ad-hoc script | Windows console text encoding | Prefix the run with `PYTHONIOENCODING=utf-8` |
| `measure.py` cannot find a file | Benchmark data is missing | See section 7 |
| Monitoring stops at the Azure check, or the token command errors | Your account does not have Reader on `APPS_EU_PROD` | A permissions request, not a setup problem — raise it with the platform team |

### Known quirks — read before trusting output

- **Monitoring:** `report.py` cannot honour a 24-hour pin; it re-pins the window itself. Pin with
  `cyclewin.py new --window 24h` and collect with `collect.py`.
- **CP monitoring:** step 4 omits Http5xx from the saved output. Run `healthcheck.py` separately
  for those figures.
- **TeamHub:** the workbook computes `Availability %` independently of the `num_failed_requests`
  column beside it, so the two do not always reconcile. Bands follow availability.
- **Triage:** root cause is a *suggestion*, measured around 44%. Confirm before saving.

---

On macOS the same steps apply — use `brew install` in place of `winget install`, and
`curl -fsSL https://claude.ai/install.sh | bash` for Claude Code.
