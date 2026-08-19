#!/usr/bin/env python
"""Run the six TeamHub monitoring steps for the pinned window, return one dict.

  1  KPI availability      workbook Teamhub section
  2  Availability tests    6 synthetic tests
  3  App Service           plan CPU/memory + site 5xx, response time, working set
  4  SQL database          DTU, storage, sessions, connections, deadlocks
  5  Application failures  TeamHub's own failing endpoints and exceptions, API + mobile
  6  Alerts                both components

Scope is TeamHub only. Downstream Proton health is deliberately not measured here
— it is Customer Portal's cycle that owns it, and duplicating it would produce two
reports arguing about the same numbers.
"""
import json, urllib.parse

import cyclewin, run_kpi, q, azure, estate

q.APPIDS.update(estate.APPIDS)


# ---------------------------------------------------------------- helpers

def rows(res):
    if not res or not res.get('tables'):
        return []
    t = res['tables'][0]
    cols = [c['name'] for c in t['columns']]
    return [dict(zip(cols, r)) for r in t['rows']]


def band(value, red, amber, higher_is_better=True):
    if value is None:
        return 'none'
    if higher_is_better:
        if value < red:   return 'crit'
        if value < amber: return 'warn'
        return 'ok'
    if value >= red:   return 'crit'
    if value >= amber: return 'warn'
    return 'ok'


def rid(kind, name, extra=''):
    base = f'/subscriptions/{estate.SUB}/resourceGroups/{estate.RG}/providers'
    return {
        'site': f'{base}/Microsoft.Web/sites/{name}',
        'plan': f'{base}/Microsoft.Web/serverfarms/{name}',
        'sqldb': f'{base}/Microsoft.Sql/servers/{name}/databases/{extra}',
    }[kind]


def summarise_metric(payload):
    """peak  = highest 5-minute AVERAGE. Alert rules evaluate averages, so this is
              the only figure we may band on.
       spike = highest 5-minute MAXIMUM. Reported for context only — a momentary
              spike inside a bucket is not a threshold breach, and banding on it
              would raise criticals the configured alerts would never fire."""
    avg = azure.flat(payload, 'average')
    mx = azure.flat(payload, 'maximum')
    tot = azure.flat(payload, 'total')
    vals = [v for _, v in (avg or tot or mx)]
    if not vals:
        return None
    return {
        'mean': round(sum(vals) / len(vals), 2),
        'peak': round(max(vals), 2),
        'spike': round(max(v for _, v in mx), 2) if mx else None,
        'total': round(sum(v for _, v in tot), 2) if tot else None,
        'samples': len(vals),
    }


# ---------------------------------------------------------------- 1  KPIs

def step_kpis(span, start, end, grain):
    """The workbook computes every TeamHub KPI in one query, returning one row
    per feature — so a single tile yields all nine KPIs."""
    out = []
    for tile in run_kpi.load_tiles(estate.WORKBOOK_SECTION):
        kql = (tile.get('query') or '').strip()
        if not kql or tile.get('vis') != 'tiles':
            continue
        res, err = run_kpi.run(run_kpi.substitute(kql, start, end, grain),
                               tile['resources'], span)
        if err:
            out.append({'name': '(query failed)', 'error': err, 'band': 'none'})
            continue
        for r in rows(res):
            avail = r.get('Availability %')
            out.append({
                'name': r.get('title') or r.get('feature') or '(untitled)',
                'avail': avail,
                'requests': r.get('total_requests') or 0,
                'failed': r.get('num_failed_requests') or 0,
                'band': band(avail, estate.KPI_BANDS['red'], estate.KPI_BANDS['amber']),
            })
    out.sort(key=lambda k: (k['avail'] is not None, k['avail'] if k['avail'] is not None else 0))
    return out


# ---------------------------------------------------------------- 2  tests

AVAIL_KQL = """
availabilityResults
| extend ok = tostring(success) == "1"
| summarize Runs=count(), Failed=countif(not(ok)),
            AvgMs=round(avg(duration),0) by Test=name
| extend Avail=round(100.0*(Runs-Failed)/Runs,3)
| project Test, Avail, Runs, Failed, AvgMs
| sort by Avail asc
"""


def step_availability(span):
    res, err = q.query(AVAIL_KQL, [estate.API], span)
    tests = rows(res)
    if err or not tests:
        return {'error': err or 'no availability tests returned data', 'band': 'none', 'tests': []}
    runs = sum(t['Runs'] for t in tests)
    failed = sum(t['Failed'] for t in tests)
    avail = round(100.0 * (runs - failed) / runs, 3) if runs else None
    return {
        'avail': avail, 'runs': runs, 'failed': failed,
        'tests_total': len(tests), 'tests_ok': sum(1 for t in tests if t['Failed'] == 0),
        'tests': tests,
        'band': band(avail, estate.KPI_BANDS['red'], estate.KPI_BANDS['amber']),
    }


# ---------------------------------------------------------------- 3  app service

def step_appservice(span):
    out = {'plan': estate.PLAN, 'site': estate.SITE, 'plan_metrics': {}, 'site_metrics': {}}

    for name in ('CpuPercentage', 'MemoryPercentage'):
        payload, err = azure.metric(rid('plan', estate.PLAN), name, 'Average,Maximum',
                                    span, split_instance=True)
        if err:
            out['plan_metrics'][name] = {'error': err[:120]}
            continue
        per = azure.by_instance(payload, 'average')
        if not per:
            out['plan_metrics'][name] = {'no_data': True}
            continue
        out['instances'] = len(per)
        allv = [v for s in per.values() for _, v in s]
        b = estate.PLAN_BANDS[name]
        peak = round(max(allv), 2)
        out['plan_metrics'][name] = {
            'mean': round(sum(allv) / len(allv), 2), 'peak': peak,
            'band': band(peak, b['red'], b['amber'], higher_is_better=False),
            'headroom': round(b['red'] - peak, 1),
        }

    for name, agg in (('Http5xx', 'Total'), ('HttpResponseTime', 'Average,Maximum'),
                      ('AverageMemoryWorkingSet', 'Average,Maximum')):
        payload, err = azure.metric(rid('site', estate.SITE), name, agg, span)
        if err:
            out['site_metrics'][name] = {'error': err[:120]}
            continue
        s = summarise_metric(payload)
        if not s:
            out['site_metrics'][name] = {'no_data': True}
            continue
        b = estate.SITE_BANDS[name]
        s['band'] = band(s['peak'], b['red'], b['amber'], higher_is_better=False)
        out['site_metrics'][name] = s

    bands = [m.get('band') for m in list(out['plan_metrics'].values()) + list(out['site_metrics'].values())
             if m.get('band')]
    out['band'] = 'crit' if 'crit' in bands else ('warn' if 'warn' in bands else 'ok')
    # There is no health probe on this site: healthCheckPath is null and alwaysOn
    # is false, so no HealthCheckStatus metric is emitted at all.
    out['health_probe'] = None
    return out


# ---------------------------------------------------------------- 4  sql

def step_sql(span):
    r = rid('sqldb', estate.SQL_SERVER, estate.SQL_DB)
    out = {'server': estate.SQL_SERVER, 'database': estate.SQL_DB,
           'tier': estate.SQL_TIER, 'metrics': {}}
    for name, agg in (('dtu_consumption_percent', 'Average,Maximum'),
                      ('storage_percent', 'Maximum'),
                      ('sessions_percent', 'Average,Maximum'),
                      ('connection_failed', 'Total'),
                      ('deadlock', 'Total'),
                      ('cpu_percent', 'Average,Maximum')):
        payload, err = azure.metric(r, name, agg, span, interval='PT15M')
        if err:
            out['metrics'][name] = {'error': err[:120]}
            continue
        s = summarise_metric(payload)
        if not s:
            out['metrics'][name] = {'no_data': True}
            continue
        if name in estate.SQL_BANDS:
            b = estate.SQL_BANDS[name]
            s['band'] = band(s['peak'], b['red'], b['amber'], higher_is_better=False)
            s['headroom'] = round(b['red'] - s['peak'], 1)
        elif name in ('connection_failed', 'deadlock'):
            s['band'] = 'ok' if (s.get('total') or 0) == 0 else 'warn'
        out['metrics'][name] = s
    bands = [m.get('band') for m in out['metrics'].values() if m.get('band')]
    out['band'] = 'crit' if 'crit' in bands else ('warn' if 'warn' in bands else 'ok')
    return out


# ---------------------------------------------------------------- 5  failures

REQ_FAIL_KQL = """
requests
| extend failed = tostring(success) == "False"
| summarize Total=sum(itemCount), Failures=sumif(itemCount, failed),
            Codes=make_set(resultCode, 4) by Endpoint=operation_Name
| where Failures > 0 and Total >= {MIN}
| extend FailPct=round(100.0*Failures/Total,2)
| where FailPct >= {PCT}
| sort by Failures desc
"""

EXC_KQL = """
exceptions
| summarize Count=sum(itemCount), Sample=any(outerMessage) by Type=type, Method=method
| where Count >= {MIN}
| sort by Count desc
"""

REQ_SUM_KQL = """
requests
| summarize Total=sum(itemCount), Failures=sumif(itemCount, tostring(success)=="False")
| extend FailPct=round(100.0*Failures/Total,3)
"""


def step_failures(span):
    out = {'min_calls': estate.FAIL_MIN_CALLS, 'fail_pct': estate.FAIL_PCT,
           'exception_min': estate.EXCEPTION_MIN}

    summ = rows(q.query(REQ_SUM_KQL, [estate.API], span)[0])
    s = summ[0] if summ else {}
    out['total'] = s.get('Total')
    out['failures'] = s.get('Failures')
    out['pct'] = s.get('FailPct')

    kql = (REQ_FAIL_KQL.replace('{MIN}', str(estate.FAIL_MIN_CALLS))
                       .replace('{PCT}', str(estate.FAIL_PCT)))
    res, err = q.query(kql, [estate.API], span)
    out['endpoints'] = [] if err else rows(res)
    for e in out['endpoints']:
        e['band'] = 'crit' if e['FailPct'] >= 50 else 'warn'

    exc_kql = EXC_KQL.replace('{MIN}', str(estate.EXCEPTION_MIN))
    for role, comp in estate.COMPONENTS:
        res, err = q.query(exc_kql, [comp], span)
        out[f'exceptions_{role.lower()}'] = [] if err else rows(res)[:8]
    return out


# ---------------------------------------------------------------- 6  alerts

def step_alerts(start_iso, end_iso):
    comps, fired = [], []
    for role, comp in estate.COMPONENTS:
        r = (f'/subscriptions/{estate.SUB}/resourceGroups/{estate.RG}'
             f'/providers/Microsoft.Insights/components/{comp}')
        qs = urllib.parse.urlencode({'api-version': '2019-05-05-preview',
                                     'customTimeRange': f'{start_iso}/{end_iso}',
                                     'targetResource': r})
        data, err = azure.get(f'{azure.ARM}/subscriptions/{estate.SUB}'
                              f'/providers/Microsoft.AlertsManagement/alerts?{qs}')
        if err:
            comps.append({'role': role, 'component': comp, 'error': err[:120]})
            continue
        items = data.get('value', [])
        for a in items:
            p = a['properties']['essentials']
            fired.append({
                'component': comp, 'role': role,
                'rule': p.get('alertRule', '').split('/')[-1],
                'sev': (p.get('severity') or '').replace('Sev', ''),
                'state': p.get('alertState'), 'condition': p.get('monitorCondition'),
                'fired': p.get('startDateTime', '')[:19].replace('T', ' '),
                'resolved': (p.get('monitorConditionResolvedDateTime') or '')[:19].replace('T', ' '),
            })
        comps.append({'role': role, 'component': comp, 'fired': len(items),
                      'band': 'ok' if not items else 'warn'})
    fired.sort(key=lambda f: f['fired'])
    return {'components': comps, 'fired': fired,
            'unacknowledged': sum(1 for f in fired if f['state'] == 'New'),
            'still_firing': sum(1 for f in fired if f['condition'] == 'Fired')}


def collect():
    start, end, grain, span, label, pinned = cyclewin.resolve(None)
    win = cyclewin.load() or {}
    return {
        'estate': 'TeamHub',
        'window': {
            'start': win.get('start'), 'end': win.get('end'),
            'start_local': win.get('start_local'), 'end_local': win.get('end_local'),
            'shift': win.get('shift'), 'label': win.get('label'),
            'span_h': win.get('span_h'), 'grain': grain, 'pinned_at': win.get('pinned_at'),
        },
        'kpis': step_kpis(span, start, end, grain),
        'availability': step_availability(span),
        'appservice': step_appservice(span),
        'sql': step_sql(span),
        'failures': step_failures(span),
        'alerts': step_alerts(win.get('start'), win.get('end')),
    }


if __name__ == '__main__':
    print(json.dumps(collect(), indent=1, default=str))
