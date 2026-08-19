# Jira process

How monitoring findings get recorded. Read before touching Jira.

## Hierarchy

```
MST-77626   Customer Portal Availability KPI 2026        umbrella Incident, project MST
  └─ MST-77627   ... - Login                              per-KPI Incident
       └─ CP-95346   Q3 - ... - Login                     Investigation task
            │        ↑ THE EVIDENCE TABLE IS IN THIS DESCRIPTION
            ├─ CP-95498  DEV Investigation                Sub-task
            └─ CP-95734  DEV Investigation                Sub-task
```

Nine Q3 Investigation tasks exist, one per step-1 KPI:

```jql
project = CP AND issuetype = "Investigation task"
  AND summary ~ "Q3 - Customer Portal Availability KPI 2026"
```

Quarter rolls — check for the current quarter's set rather than assuming Q3.

## The evidence table

In the **Investigation task description**: `Date | <KPI> (%Availability) | Dev investigation`

- Rows are **weekly ranges, Monday to Monday**.
- Every KPI gets a weekly row **even at 100%**.
- A **red** drop (< 99.0%) gets an **extra row dated the day it was noticed**.
- Amber alone does not earn a dated row.
- The investigation cell holds evidence plus the ticket handling the cause.

## Rules

1. **Scan before filing.** Search for an existing active ticket first. If one covers it,
   record the finding and cite that number. Do not raise a duplicate.
2. **Post as a comment. Never edit a description.** Descriptions are other people's work,
   and a markdown round-trip risks destroying embedded screenshots and smartlinks.
3. **Screenshots not required.** A text outcome breakdown with counts is accepted:
   `Proton:Timeout 34 · Titan:ContactReplicationDelay 28 · Unknown 19`.
4. **Route by where the failure is.** Proton API failing → PAPI directly. Standalone CP
   ticket where needed.
5. **Infra/alerting coverage gaps are flag-only.** Missing or mis-scoped Azure alert rules
   belong to the infra team. Surface them in the report; do not raise tickets.
6. **Never create an issue without explicit approval.** Draft it in full, present it, wait.
   Approval for one ticket does not carry to the next.

Rule 1 is not theoretical. A finding once reached "draft at Highest priority" before a scan
revealed 28 prior tickets, correct-by-design behaviour, and an active owning fix. See
`known-issues.md`.

## Ticket house style

Investigation tasks in PAPI follow:

> **Summary:** Investigate Proton Failures on `<endpoint>` – `<date>`
>
> Hi Proton Team
>
> During CustomerPortal daily monitoring process, multiple failed requests on Proton
> `<endpoint>` have been detected. Please investigate.
>
> Details:
> - N failed requests out of M for last Xh
> - links to App Insights / Log Analytics

## Known causes already on record

| KPI | Cause | Ticket |
|---|---|---|
| Login | `Titan:ContactReplicationDelay` | ENHANCE-9356 (closed, children open) |
| Login | Proton timeout post-release, INC0762433 | PAPI-81775 → CEN-49020 |
| Login | 424s on companies + HR endpoint | PAPI-82063 |
| Create Booking | sampling unknowns | PAPI-78249, TTN-140324, TTN-140980 |
| Pay Centre Balance | `Unknown:ResponseSampled` | TTN-145479 |
| Proton `POST /convert` | 500s at ~55% | PAPI-81755 — stalled since 13 Jul 2026 |
