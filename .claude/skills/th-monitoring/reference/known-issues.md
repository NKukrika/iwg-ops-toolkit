# TeamHub — known issues and interpretation notes

Check before reporting anything as new.

---

## Interpretation — read these before judging a number

**Volume swings roughly 20× between weekday and weekend.** TeamHub is a staff tool, so
Sunday traffic is a fraction of Tuesday's. Low volume inflates percentage impact — a handful
of failures can drop a KPI into amber on a quiet day with nothing having changed. **Always
read the request count next to the percentage, and say so in the report.**

**Several KPIs run at very low volume.** Edit Service has been seen at 4 requests in a day.
One failure there reads as 75% availability. Judge on absolute counts as well as rate.

**Band on the average, never the maximum.** Observed in a single window: response time
spiking to **55.6s** while the 5-minute average peaked at **0.56s**, and SQL DTU spiking to
**77%** while the average peaked at **2.08%**. Both spikes are real and both are harmless —
the alert rules evaluate averages. Reporting either as a breach would be wrong.

**The plan runs one instance.** There is no redundancy at the plan level and no per-instance
comparison to draw. The splitting code is retained so it stays correct if the plan is ever
scaled out.

---

## Accepted configuration — do not report these

Confirmed with the user on 2026-08-16. These are known and accepted. **Do not raise them as
findings, and do not list them under "flagged to infra" in the report.**

**No health probe on the site.** `we-teamhub-prod-app-1` has `healthCheckPath: null` and
`alwaysOn` false, so no `HealthCheckStatus` metric is emitted. Accepted — on a single-instance
plan there is nowhere to reroute to anyway. Step 3 still reports the App Service metrics that
do exist; it simply stops commenting on the missing probe.

**No alert rules on the SQL database.** `teamhub-api` has no Azure alerts configured.
Accepted. **Keep running step 4** — the DTU, storage and connection figures are still worth
reporting each cycle — but do not flag the absence of alert rules as a gap. Continue to label
the bands as our own convention, since that affects how the numbers should be read.

## Still open — confirm before reporting

**One availability alert is disabled.** `iwg - teamhub - api-we-teamhub-prod-insights-1`
(webtest, 5 failed locations, Sev1) is **off**, while the other five webtest alerts — login,
pricing-permissions, localisation, get-status, business-rule-engine — are enabled. The
underlying test itself runs normally (2,016 runs at 100% in a recent window); only its alert
is off. Confirm whether that is deliberate before reporting it; the equivalent situation on
Customer Portal turned out to be intentional.

---

## Known dependency behaviour

TeamHub makes roughly **4.3 million calls per week** to Proton (`api.proton-graph.cloud`),
plus ~1.8M to `iam-fr.iwgplc.com` and ~71K to `payments.ingena-int.work`.

Downstream Proton health is **not** measured by this cycle — Customer Portal owns it. But a
Proton fault will surface here as TeamHub request failures or exceptions, and when it does it
is a **PAPI** ticket.

The one to know about: `POST /products/pricelist/spaceinventory/api/v1/renewal-actions/calculate-prices`
returns **403** at roughly 8% of calls. This is the endpoint behind **CEN-49020** — the
infinite loop fixed in H26.08.0 on 5 August 2026. **The loop is fixed; the 403 is not.**

---

## Observed exception types

Routinely present on the mobile component; establish whether a count is abnormal before
reporting it:

- `System.Net.Sockets.SocketException` — tens per day, consistent with mobile clients on
  unreliable networks
- `System.Exception` — generic, needs the message to be useful

The API component typically produces no exception type above the reporting floor.
