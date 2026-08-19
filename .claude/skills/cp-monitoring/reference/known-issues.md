# Known issues — check before reporting

Several high-volume failures in this estate are expected behaviour, deliberate config, or
already owned. Reporting them as new findings wastes other teams' time.

---

## Proton `GET /ClientClaims/GetClientValue` — 100% 404, do not re-raise

Appears in every step-5 scan with tens of thousands of failures and a 100% failure rate.
**This is not a fault.**

- The endpoint reads the `r:tuid` claim for a ClientId from `admin.ClientClaims`. No claim
  → 404. That is **correct API behaviour** — confirmed in PAPI-80088 (closed, *No action
  required*) and TTN-141955.
- The caller is the **Titan Event Broker** (`ServiceBusProcessor.ProcessMessage`) sending
  the wrong ClientId — `Titan` instead of the migrated GUID identity. `TitanApplication` is
  the variant that carries `r:tuid=125`.
- Root cause is Titan-side: `-x-ctx-systemid` hardcoded to `"Titan"` in
  `Regus.Titan.Objects/Constants.cs:556`, sent from `PaymentApiClient.cs:90`. After the
  IS4→IAM/FR migration that literal no longer resolves.
- **Impact is audit-trail only** — no functional payment failure. Affected transactions are
  attributed to fallback user "1".
- **Active owning ticket: TTN-145447** (Open, Critical, fixVersion PlannedHotfix).

Volume is not a useful signal either — PAPI-81284 logged 45.43k failures in 8h in June 2026.
It has been observed above 60k in 24h. Cite TTN-145447 and move on.

## Proton `GET /` — root-path probing

Around 1,800 failures/day as 403/404 across ~22 roles, clustered against staging roles.
Clears the 1,500 threshold numerically but reads as root-path probing rather than a broken
feature. Not worth a ticket without a specific reason.

---

## Deliberate config that looks wrong

Confirmed intentional. Do not report as findings:

- **`Pantheon KPI Alert - Credit Card registration failures P1 - TEST SNOW MAPPING`** —
  enabled, Sev1, threshold `>= 20000` failures / 5 min. Exists for ServiceNow mapping
  tests, not for coverage. It has fired.
- **`Pantheon KPI Alert - Login - ProfileNotFound 502 anomaly detection P1`** — disabled,
  Sev1, despite carrying a major-incident runbook in its query header. Intentionally off.

Several alert names also do not match their thresholds — `api-01-http5xx-greaterthan-50` is
actually 250, `applinux-01-httpresponsetime-greaterthan-7` is actually 30. Cosmetic, but
misleading if read during an incident.

---

## Open coverage gaps — flagged to infra, not actioned

Surface these in reports; do not raise tickets.

- **`we-prod-pantheon-applinux-01` has no `HealthCheckStatus` alert.** The `api-01` and
  `mcp-01` sites both do. Probe failures on the Web site raise nothing — and Web is the
  tier serving `myregus.com` and 19 other customer hostnames.
- **The plan memory rule cannot see single-instance breaches.** It averages across all
  instances, so one instance at 80.4% against an 80% threshold cannot fire.
- **MCP alerts sit on a third component.** `we-prod-pantheon-appins-mcp-01` appears on
  neither the Web nor the API alerts blade — an alert firing there is invisible to anyone
  checking only those two. This is the likely reason a Sev2 lead-stoppage alert once went
  six hours unacknowledged.

---

## Interpretation notes

- **`De-Provision Call Answering` reports no data.** Zero requests is normal for this
  journey — it does not mean the KPI is broken, but it does mean a genuine failure would
  be indistinguishable from an idle period. Report as ⚪, not as a fault.
- **`Submit Lead (AI Agent)` is low volume** (tens of requests/day). One failure moves the
  percentage a long way. Judge it on volume as well as rate — a total stoppage still shows
  100% availability, because the KPI measures success rate and zero-of-zero is green.
- **The Login KPI excludes `Func:`-classified outcomes** by design, so user-error cases
  like "no access to staff mode" are already filtered out. The remaining failures are
  genuine platform failures.
