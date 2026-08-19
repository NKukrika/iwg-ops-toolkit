# Jira process — TeamHub

How monitoring findings get recorded. Read before touching Jira.

## Hierarchy

```
MST      TeamHub Availability KPI 2026                      umbrella Incident
  └─ CEN-48974   Q3 - TeamHub Availability KPI 2026 - Create Order    Investigation task
       │         ↑ THE EVIDENCE TABLE IS IN THIS DESCRIPTION
       ├─ CEN-49046   Dev Investigation of CEN-48974                  Sub-task
       └─ CEN-49003   Dev Investigation of CEN-48974                  Sub-task
```

One Q3 Investigation task exists per KPI — Create Order, Edit Service, Add Service, and so
on. Find the current set with:

```jql
project = CEN AND issuetype = "Investigation task"
  AND summary ~ "Q3 - TeamHub Availability KPI 2026"
```

The quarter rolls — check for the current quarter rather than assuming Q3.

## The evidence table

In the **Investigation task description**: `Date | <KPI> (%Availability) | Dev investigation`

- Rows are **weekly ranges, Monday to Monday**.
- Every KPI gets a weekly row **even at 100%**.
- A **red** drop (< 99.0%) gets an **extra row dated the day it was noticed**.
- Amber alone does not earn a dated row.
- The investigation cell holds evidence plus the ticket handling the cause.

## Rules

1. **Scan before filing.** Search for an existing active ticket first. If one covers the
   issue, record the finding and cite that number rather than raising a duplicate.
2. **Post as a comment. Never edit a description.** Descriptions are other people's work,
   and a markdown round-trip risks destroying embedded screenshots and smartlinks.
3. **Screenshots not required.** A text breakdown with counts is accepted.
4. **Route by where the failure is.** TeamHub calls Proton heavily, so a genuine Proton
   fault will surface here as TeamHub request failures — that is a **PAPI** ticket, not a
   CEN one, even though TeamHub's monitoring found it. Only file in CEN when the fault is
   TeamHub's own.
5. **Infra/alerting coverage gaps are flag-only.** Missing probes, missing alert rules and
   mis-scoped thresholds belong to the infra team. Surface them; do not raise tickets.
6. **Never create an issue without explicit approval.** Draft it in full, present it, wait.
   Approval for one ticket does not carry to the next.

## Ticket house style

Investigation tasks follow the pattern used across the estate:

> **Summary:** Investigate TeamHub failures on `<endpoint>` – `<date>`
>
> Hi Team
>
> During TeamHub daily monitoring process, multiple failed requests have been detected on
> the following endpoint: `<endpoint>`. Please investigate.
>
> Details:
> - N failed requests out of M over the monitored window
> - result codes observed
> - the pinned window in UTC

## Related history worth knowing

**CEN-49020** — *"Investigate infinite request loop triggered by price calculation failure"*.
Changing End Date or Month-to-month on *Amend Upcoming Renewal* triggered
`POST calculateAgreementPrices`; when it failed, the error handler restored the fields, which
re-raised their own change handlers and re-fired the calculation in a self-sustaining loop.
The in-flight guard was set after an `await`, so it never held. Kicked off by a **403** from
the Proton dependency `renewal-actions/calculate-prices`.

Fixed in **H26.08.0 (2.81.1)**, released 5 August 2026. The loop is gone; **the underlying
403 is not**. It was still occurring at ~8% of calls afterwards.

This is the clearest example of rule 4 in practice: a TeamHub front-end bug amplifying a
Proton fault, which then degraded *Customer Portal* KPIs on 14–15 July 2026. Three systems,
one incident, and the KPI that registered it belonged to none of them.
