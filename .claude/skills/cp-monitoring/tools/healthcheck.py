#!/usr/bin/env python
"""Step 4 -- App Service Health Check status, split by instance.

HealthCheckStatus is reported as a percentage: 100 = the instance passed its
health probe, 0 = it failed. An instance that stays at 0 past the configured
threshold gets removed from the load balancer and replaced.

  python healthcheck.py            # pinned cycle window
  python healthcheck.py --window 4h
"""
import argparse, json, urllib.parse, urllib.request, urllib.error
from collections import defaultdict

import cyclewin
from metrics import token, ARM, SUB, RG

SITES = [
    ('Web', 'we-prod-pantheon-applinux-01', '/home'),
    ('API', 'we-prod-pantheon-applinux-api-01', '/api/ping'),
]


def fetch(site, metric, aggs, span, interval='PT5M', split=True):
    rid = (f'/subscriptions/{SUB}/resourceGroups/{RG}'
           f'/providers/Microsoft.Web/sites/{site}')
    q = {'api-version': '2018-01-01', 'metricnames': metric,
         'aggregation': aggs, 'timespan': span, 'interval': interval}
    if split:
        q['$filter'] = "Instance eq '*'"
    url = f'{ARM}{rid}/providers/microsoft.insights/metrics?{urllib.parse.urlencode(q)}'
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


def series(payload, key='average'):
    per = defaultdict(list)
    for m in payload.get('value', []):
        for ts in m.get('timeseries', []):
            inst = next((mv['value'] for mv in ts.get('metadatavalues', [])
                         if mv['name']['value'].lower() == 'instance'), '(all)')
            for pt in ts.get('data', []):
                if pt.get(key) is not None:
                    per[inst].append((pt['timeStamp'], pt[key]))
    return per


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--window', default=None)
    a = ap.parse_args()
    start, end, grain, span, label, pinned = cyclewin.resolve(a.window)

    print(f'WINDOW : {label}')
    print(f'         {start:%Y-%m-%d %H:%M:%S} -> {end:%Y-%m-%d %H:%M:%S} UTC')
    print('HEALTH : 100 = probe passing, <100 = probe failing on that instance')

    for role, site, path in SITES:
        print('\n' + '=' * 78)
        print(f'{role}  -  {site}   probe: {path}')
        print('=' * 78)

        payload, err = fetch(site, 'HealthCheckStatus', 'Average,Minimum', span)
        if err:
            print(f'  HealthCheckStatus: ERROR {err}')
            continue
        per = series(payload, 'average')
        mins = series(payload, 'minimum')
        if not per:
            print('  HealthCheckStatus: no data')
        else:
            allvals = [v for vals in per.values() for _, v in vals]
            overall = round(sum(allvals) / len(allvals), 3)
            unhealthy_pts = sum(1 for v in allvals if v < 100)
            print(f'\n  Overall health {overall}%   instances={len(per)}   '
                  f'samples={len(allvals)}   degraded samples={unhealthy_pts}')
            print(f'    {"instance":<18} {"avg":>7} {"min":>6} {"samples":>8} {"<100":>6}  state')
            for inst, vals in sorted(per.items(), key=lambda kv: sum(v for _, v in kv[1]) / len(kv[1])):
                v = [x for _, x in vals]
                mn = min((x for _, x in mins.get(inst, [])), default=min(v))
                bad = sum(1 for x in v if x < 100)
                avg = round(sum(v) / len(v), 2)
                state = 'HEALTHY' if bad == 0 else ('DEGRADED' if avg >= 99 else 'UNHEALTHY')
                print(f'    {inst[:18]:<18} {avg:>7} {mn:>6} {len(v):>8} {bad:>6}  {state}')
            # when did it dip
            dips = sorted({t for vals in per.values() for t, v in vals if v < 100})
            if dips:
                print(f'    first dip {dips[0]}   last dip {dips[-1]}   distinct intervals={len(dips)}')

        # Site-level 5xx for corroboration
        p5, e5 = fetch(site, 'Http5xx', 'Total', span, interval='PT1H', split=False)
        if not e5:
            pts = [(pt['timeStamp'], pt.get('total') or 0)
                   for m in p5.get('value', []) for ts in m.get('timeseries', [])
                   for pt in ts.get('data', [])]
            tot = sum(v for _, v in pts)
            worst = max(pts, key=lambda kv: kv[1]) if pts else None
            print(f'\n  Http5xx total={int(tot)}'
                  + (f'   worst hour {worst[0]} = {int(worst[1])}' if worst and worst[1] else ''))


if __name__ == '__main__':
    main()
