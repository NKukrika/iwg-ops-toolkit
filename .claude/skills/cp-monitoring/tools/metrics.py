#!/usr/bin/env python
"""Step 3 — App Service Plan CPU / Memory, split by instance.

Reads the pinned cycle window so it lines up with steps 1 and 2.

  python metrics.py                 # both plans, pinned window
  python metrics.py --window 4h     # ad hoc override
"""
import argparse, io, json, shutil, subprocess, sys, urllib.parse
from collections import defaultdict

import cyclewin

AZ = shutil.which('az') or r'C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd'
SUB = 'a464f508-ff11-423c-bab6-8eadb42ebcf2'
RG = 'RG_WE_APPS_PANTHEON_PROD'

PLANS = [
    ('Web', 'we-prod-pantheon-serplan-01'),
    ('API', 'we-prod-pantheon-serplan-api-01'),
]

# Sev1 metric-alert thresholds configured on both plans. The amber "approaching"
# band is our own convention, not Azure config -- flagged as such in the report.
BANDS = {
    'CpuPercentage':    {'red': 90.0, 'amber': 80.0},
    'MemoryPercentage': {'red': 80.0, 'amber': 70.0},
}


def dot(metric, value):
    if value is None:
        return 'grey'
    b = BANDS[metric]
    if value >= b['red']:
        return 'RED'
    if value >= b['amber']:
        return 'AMBER'
    return 'green'


ARM = 'https://management.azure.com'
_TOK = None


def token():
    """Call ARM directly -- az.cmd routes through cmd.exe, which eats the & in query strings."""
    global _TOK
    if _TOK is None:
        p = subprocess.run([AZ, 'account', 'get-access-token', '--resource', ARM,
                            '--query', 'accessToken', '-o', 'tsv'],
                           capture_output=True, text=True)
        if p.returncode:
            raise SystemExit('token failed: ' + (p.stderr or p.stdout)[:300])
        _TOK = p.stdout.strip()
    return _TOK


def fetch(plan, metric, aggs, span, interval='PT5M'):
    import urllib.request, urllib.error
    rid = (f'/subscriptions/{SUB}/resourceGroups/{RG}'
           f'/providers/Microsoft.Web/serverfarms/{plan}')
    qs = urllib.parse.urlencode({
        'api-version': '2018-01-01',
        'metricnames': metric,
        'aggregation': aggs,
        'timespan': span,
        'interval': interval,
        '$filter': "Instance eq '*'",
    })
    url = f'{ARM}{rid}/providers/microsoft.insights/metrics?{qs}'
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token()})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        d = e.read().decode(errors='replace')
        try:
            d = json.loads(d)['error']['message']
        except Exception:
            d = d[:300]
        return None, f'HTTP {e.code} {d}'
    except Exception as e:
        return None, f'{type(e).__name__}: {e}'


def summarise(payload):
    """Per-instance roll-up.

    peak  = highest 5-minute AVERAGE. This is the basis the Sev1 metric alerts
            evaluate, so it is what we band on.
    spike = highest 5-minute MAXIMUM -- a momentary sample, reported for context
            only. Banding on spike would overstate risk against the alert config.
    """
    per = defaultdict(lambda: {'avg': [], 'max': []})
    for m in payload.get('value', []):
        for ts in m.get('timeseries', []):
            inst = next((mv['value'] for mv in ts.get('metadatavalues', [])
                         if mv['name']['value'].lower() == 'instance'), '(unsplit)')
            for pt in ts.get('data', []):
                if pt.get('average') is not None:
                    per[inst]['avg'].append(pt['average'])
                if pt.get('maximum') is not None:
                    per[inst]['max'].append(pt['maximum'])
    out = {}
    for inst, d in per.items():
        if not d['avg']:
            continue
        out[inst] = {
            'avg': round(sum(d['avg']) / len(d['avg']), 2),
            'peak': round(max(d['avg']), 2),
            'spike': round(max(d['max']), 2) if d['max'] else None,
            'samples': len(d['avg']),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--window', default=None)
    a = ap.parse_args()
    start, end, grain, span, label, pinned = cyclewin.resolve(a.window)

    print(f'WINDOW : {label}')
    print(f'         {start:%Y-%m-%d %H:%M:%S} -> {end:%Y-%m-%d %H:%M:%S} UTC')
    print(f'BANDS  : CPU  red>=90 (Sev1 alert)  amber>=80 (convention)')
    print(f'         MEM  red>=80 (Sev1 alert)  amber>=70 (convention)')

    for role, plan in PLANS:
        print('\n' + '=' * 78)
        print(f'{role}  -  {plan}')
        print('=' * 78)
        for metric in ('CpuPercentage', 'MemoryPercentage'):
            payload, err = fetch(plan, metric, 'Average,Maximum', span)
            if err:
                print(f'  {metric}: ERROR {err}')
                continue
            s = summarise(payload)
            if not s:
                print(f'  {metric}: no data')
                continue
            allavg = [v['avg'] for v in s.values() if v['avg'] is not None]
            peak = max(v['peak'] for v in s.values())
            mean = round(sum(allavg) / len(allavg), 2) if allavg else None
            print(f'\n  {metric}   instances={len(s)}  '
                  f'mean={mean}%  peakAvg={peak}%  [{dot(metric, peak)}]')
            print(f'    {"instance":<18} {"avg%":>7} {"peakAvg%":>9} {"spike%":>7} {"samples":>8}  band')
            for inst, v in sorted(s.items(), key=lambda kv: -kv[1]['peak']):
                print(f'    {inst[:18]:<18} {v["avg"]:>7} {v["peak"]:>9} '
                      f'{str(v["spike"]):>7} {v["samples"]:>8}  {dot(metric, v["peak"])}')


if __name__ == '__main__':
    main()
