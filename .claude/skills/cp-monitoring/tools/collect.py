#!/usr/bin/env python
"""Run all six monitoring steps for the pinned window and return one result dict.

Kept separate from rendering so the same collected data can be written as HTML,
JSON, or anything else without re-querying Azure.
"""
import json, subprocess, urllib.error, urllib.parse, urllib.request

import cyclewin, run_kpi, q, metrics, healthcheck

SUB = 'a464f508-ff11-423c-bab6-8eadb42ebcf2'
RG = 'RG_WE_APPS_PANTHEON_PROD'

COMPONENTS = [
    ('Web', 'we-prod-pantheon-appins-01'),
    ('API', 'we-prod-pantheon-appins-api-01'),
    ('MCP', 'we-prod-pantheon-appins-mcp-01'),
]

AVAIL_KQL = """
availabilityResults
| extend ok = tostring(success) == "1"
| summarize Runs=count(), Failed=countif(not(ok)) by Test=name
| extend Avail=round(100.0*(Runs-Failed)/Runs,3)
| project Test, Avail, Runs, Failed
| sort by Avail asc
"""

PROTON_KQL = """
requests
| extend failed = tostring(success) == "False"
| summarize Total=sum(itemCount), Failures=sumif(itemCount, failed) by Endpoint=operation_Name
| where Failures > 1500
| extend FailPct=round(100.0*Failures/Total,2)
| sort by Failures desc
"""

PROTON_SUM_KQL = """
requests
| summarize Total=sum(itemCount), Failures=sumif(itemCount, tostring(success)=="False")
| extend FailPct=round(100.0*Failures/Total,3)
"""

PROTON_DETAIL_KQL = """
requests
| extend failed = tostring(success) == "False"
| where failed
| summarize Failures=sum(itemCount) by Endpoint=operation_Name, resultCode, Role=cloud_RoleName
| sort by Failures desc
"""

PROTON_THRESHOLD = 1500


def rows(res):
    """First table of an App Insights response as a list of dicts."""
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


# ---------------------------------------------------------------- steps

def step_kpis(span, start, end, grain):
    out = []
    for tile in run_kpi.load_tiles('Customer Portal'):
        kql = tile['query']
        if not kql.strip() or tile['vis'] != 'tiles':
            continue
        res, err = run_kpi.run(run_kpi.substitute(kql, start, end, grain),
                               tile['resources'], span)
        if err:
            out.append({'name': '(query failed)', 'error': err, 'band': 'none'})
            continue
        for r in rows(res):
            avail = r.get('Availability %')
            out.append({
                'name': r.get('title') or '(untitled)',
                'avail': avail,
                'requests': r.get('total_requests') or 0,
                'failed': r.get('num_failed_requests') or 0,
                'band': band(avail, 99.0, 99.9),
            })
    out.sort(key=lambda k: (k['avail'] is not None, k['avail'] if k['avail'] is not None else 0))
    return out


def step_availability(span):
    out = []
    for role, comp in COMPONENTS[:2]:
        res, err = q.query(AVAIL_KQL, [comp], span)
        tests = rows(res)
        if err or not tests:
            out.append({'role': role, 'component': comp, 'error': err or 'no data', 'band': 'none'})
            continue
        runs = sum(t['Runs'] for t in tests)
        failed = sum(t['Failed'] for t in tests)
        avail = round(100.0 * (runs - failed) / runs, 3) if runs else None
        out.append({
            'role': role, 'component': comp,
            'avail': avail, 'runs': runs, 'failed': failed,
            'tests_total': len(tests),
            'tests_ok': sum(1 for t in tests if t['Failed'] == 0),
            'worst': [t for t in tests if t['Failed'] > 0][:5],
            'band': band(avail, 99.0, 99.9),
        })
    return out


def step_plans(span):
    out = []
    for role, plan in metrics.PLANS:
        row = {'role': role, 'plan': plan}
        for metric, key in (('CpuPercentage', 'cpu'), ('MemoryPercentage', 'mem')):
            payload, err = metrics.fetch(plan, metric, 'Average,Maximum', span)
            if err:
                row[key] = None
                continue
            s = metrics.summarise(payload)
            if not s:
                row[key] = None
                continue
            avgs = [v['avg'] for v in s.values() if v['avg'] is not None]
            row['instances'] = len(s)
            row[key] = {
                'mean': round(sum(avgs) / len(avgs), 2) if avgs else None,
                'peak': max(v['peak'] for v in s.values()),
            }
        cpu_b = band(row['cpu']['peak'], 90, 80, False) if row.get('cpu') else 'none'
        mem_b = band(row['mem']['peak'], 80, 70, False) if row.get('mem') else 'none'
        row['band'] = 'crit' if 'crit' in (cpu_b, mem_b) else ('warn' if 'warn' in (cpu_b, mem_b) else 'ok')
        if row.get('mem'):
            row['headroom'] = round(80 - row['mem']['peak'], 1)
        out.append(row)
    return out


def step_health(span):
    out = []
    for role, site, probe in healthcheck.SITES:
        payload, err = healthcheck.fetch(site, 'HealthCheckStatus', 'Average,Minimum', span)
        if err:
            out.append({'role': role, 'site': site, 'probe': probe, 'error': err, 'band': 'none'})
            continue
        per = healthcheck.series(payload, 'average')
        vals = [v for series in per.values() for _, v in series]
        if not vals:
            out.append({'role': role, 'site': site, 'probe': probe, 'error': 'no data', 'band': 'none'})
            continue
        health = round(sum(vals) / len(vals), 3)
        degraded = sum(1 for v in vals if v < 100)
        affected = sum(1 for s in per.values() if any(v < 100 for _, v in s))
        out.append({
            'role': role, 'site': site, 'probe': probe,
            'health': health, 'instances': len(per),
            'degraded': degraded, 'affected': affected,
            'band': 'ok' if degraded == 0 else ('warn' if health >= 99 else 'crit'),
        })
    return out


def step_proton(span):
    app = 'we-prod-proton-appins-proton'
    summ = rows(q.query(PROTON_SUM_KQL, [app], span)[0])
    breaches = rows(q.query(PROTON_KQL, [app], span)[0])
    detail = rows(q.query(PROTON_DETAIL_KQL, [app], span)[0])
    by_ep = {}
    for d in detail:
        by_ep.setdefault(d['Endpoint'], []).append(d)
    for b in breaches:
        top = sorted(by_ep.get(b['Endpoint'], []), key=lambda x: -x['Failures'])[:1]
        b['code'] = top[0]['resultCode'] if top else '-'
        b['role'] = (top[0]['Role'] or '').replace('we-prod-proton-', '') if top else '-'
        b['band'] = 'crit' if b['FailPct'] >= 50 else 'warn'
    s = summ[0] if summ else {}
    return {
        'total': s.get('Total'), 'failures': s.get('Failures'), 'pct': s.get('FailPct'),
        'threshold': PROTON_THRESHOLD, 'breaches': breaches,
    }


def step_alerts(start_iso, end_iso):
    comps, fired = [], []
    for role, comp in COMPONENTS:
        rid = (f'/subscriptions/{SUB}/resourceGroups/{RG}'
               f'/providers/Microsoft.Insights/components/{comp}')
        qs = urllib.parse.urlencode({
            'api-version': '2019-05-05-preview',
            'customTimeRange': f'{start_iso}/{end_iso}',
            'targetResource': rid,
        })
        url = f'https://management.azure.com/subscriptions/{SUB}/providers/Microsoft.AlertsManagement/alerts?{qs}'
        req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + metrics.token()})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read().decode()).get('value', [])
        except Exception as e:
            comps.append({'role': role, 'component': comp, 'error': str(e)[:120]})
            continue
        for a in data:
            p = a['properties']['essentials']
            fired.append({
                'component': comp, 'role': role,
                'rule': p.get('alertRule', '').split('/')[-1],
                'sev': (p.get('severity') or '').replace('Sev', ''),
                'state': p.get('alertState'),
                'condition': p.get('monitorCondition'),
                'fired': p.get('startDateTime', '')[:19].replace('T', ' '),
                'resolved': (p.get('monitorConditionResolvedDateTime') or '')[:19].replace('T', ' '),
            })
        comps.append({'role': role, 'component': comp, 'fired': len(data),
                      'band': 'ok' if not data else 'warn'})
    fired.sort(key=lambda f: f['fired'])
    return {'components': comps, 'fired': fired,
            'unacknowledged': sum(1 for f in fired if f['state'] == 'New'),
            'still_firing': sum(1 for f in fired if f['condition'] == 'Fired')}


def collect():
    start, end, grain, span, label, pinned = cyclewin.resolve(None)
    win = cyclewin.load() or {}
    return {
        'window': {
            'start': win.get('start'), 'end': win.get('end'),
            'start_local': win.get('start_local'), 'end_local': win.get('end_local'),
            'shift': win.get('shift'), 'label': win.get('label'),
            'span_h': win.get('span_h'), 'grain': grain,
            'pinned_at': win.get('pinned_at'),
        },
        'kpis': step_kpis(span, start, end, grain),
        'availability': step_availability(span),
        'plans': step_plans(span),
        'health': step_health(span),
        'proton': step_proton(span),
        'alerts': step_alerts(win.get('start'), win.get('end')),
    }


if __name__ == '__main__':
    print(json.dumps(collect(), indent=1, default=str))
