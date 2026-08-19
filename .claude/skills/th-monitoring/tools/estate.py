#!/usr/bin/env python
"""TeamHub production estate.

Every environment-specific value lives here, so a change in Azure is a one-line
edit rather than a hunt through query code.

TeamHub is a single API tier (`teamhubapi.iwgplc.com`) plus a mobile client,
backed by one App Service Plan and one SQL database. There is no web tier.
"""

SUB = 'a464f508-ff11-423c-bab6-8eadb42ebcf2'
RG = 'RG_APPS_TEAMHUB_PROD'

API = 'we-teamhub-prod-insights-1'
MOBILE = 'Teamhub-Mobile-Prod'

COMPONENTS = [('API', API), ('Mobile', MOBILE)]

APPIDS = {
    API:    '6e848f1e-195e-41f0-abcc-78b54c0883f3',
    MOBILE: '4997c27e-fac1-45c5-80b0-d93e508ceb83',
}

WORKBOOK_SECTION = 'Teamhub'

SITE = 'we-teamhub-prod-app-1'
PLAN = 'we-teamhub-prod-asp-1'
SQL_SERVER = 'we-teamhub-prod-sql-1'
SQL_DB = 'teamhub-api'

HOSTNAME = 'teamhubapi.iwgplc.com'

# ---------------------------------------------------------------- thresholds
# All taken from the alert rules configured on these resources. Where we add an
# amber band below the configured red, it is our own convention and the report
# must say so.

KPI_BANDS = {'red': 99.0, 'amber': 99.9}          # workbook tile config

PLAN_BANDS = {                                     # both alerts are Sev2
    'CpuPercentage':    {'red': 90.0, 'amber': 80.0},
    'MemoryPercentage': {'red': 90.0, 'amber': 80.0},
}

SITE_BANDS = {
    'Http5xx':                 {'red': 200.0, 'amber': 100.0},              # Sev1
    'HttpResponseTime':        {'red': 6.0, 'amber': 4.0},                  # Sev2
    'AverageMemoryWorkingSet': {'red': 5_000_000_000.0, 'amber': 4_000_000_000.0},  # Sev2
}

# SQL has no alert rules configured at all — these bands are entirely our own
# convention and must be labelled as such. The database is Basic tier, 5 DTU,
# 2 GB, which is small for a production API and is the reason this step exists.
SQL_BANDS = {
    'dtu_consumption_percent': {'red': 90.0, 'amber': 75.0},
    'storage_percent':         {'red': 90.0, 'amber': 80.0},
    'sessions_percent':        {'red': 90.0, 'amber': 75.0},
}
SQL_TIER = 'Basic, 5 DTU, 2 GB'

# ---------------------------------------------------------------- step 5
# TeamHub's own failing endpoints and exceptions. Volume swings roughly 20x
# between weekday and weekend, so an absolute failure count fires inconsistently.
# Rate with a volume floor is stable across both.
FAIL_MIN_CALLS = 20      # below this a percentage is meaningless
FAIL_PCT = 5.0           # flag at or above this failure rate
EXCEPTION_MIN = 25       # report exception types at or above this count

JIRA = {
    'project': 'CEN',
    'kpi_task_jql': ('project = CEN AND issuetype = "Investigation task" '
                     'AND summary ~ "Q3 - TeamHub Availability KPI 2026"'),
}
