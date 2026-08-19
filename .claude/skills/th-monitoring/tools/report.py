#!/usr/bin/env python
"""Run one TeamHub monitoring cycle and optionally save the report.

  python report.py --no-save
  python report.py --out "../reports"
  python report.py --shift morning
"""
import argparse, io, json, os
from datetime import datetime

import cyclewin, collect, render, estate

DEFAULT_OUT = os.environ.get('TH_REPORT_DIR') or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reports')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--shift', default=None, choices=list(cyclewin.SHIFTS) + ['auto'])
    ap.add_argument('--window', default='24h')
    ap.add_argument('--date')
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--no-save', action='store_true')
    a = ap.parse_args()

    shift = cyclewin.current_shift() if a.shift == 'auto' else a.shift
    on_date = datetime.strptime(a.date, '%Y-%m-%d').date() if a.date else None
    win = cyclewin.pin(a.window, None, shift, on_date)

    print('estate  : TeamHub')
    if win.get('label'):
        print(f"shift   : {win['label']} ({win['span_h']}h)")
        print(f"covers  : {win['start_local']} -> {win['end_local']}")
    print(f"UTC     : {win['start']} -> {win['end']}")

    d = collect.collect()

    t = {}
    for k in d['kpis']:
        t[k['band']] = t.get(k['band'], 0) + 1
    print('\n1 KPIs  : ' + ', '.join(f'{v} {k}' for k, v in sorted(t.items())))
    for k in d['kpis']:
        if k['band'] in ('warn', 'crit'):
            print(f"          {k['band']:<5} {k['name']:<24} {k['avail']}% ({k['failed']}/{k['requests']})")

    a_ = d['availability']
    print(f"2 Tests : {a_.get('avail')}%  {a_.get('tests_ok')}/{a_.get('tests_total')} clean")

    s = d['appservice']
    pm, sm = s['plan_metrics'], s['site_metrics']
    print(f"3 AppSvc: cpu peak {(pm.get('CpuPercentage') or {}).get('peak')}%  "
          f"mem peak {(pm.get('MemoryPercentage') or {}).get('peak')}%  "
          f"headroom {(pm.get('MemoryPercentage') or {}).get('headroom')} pts  "
          f"| 5xx {(sm.get('Http5xx') or {}).get('total')}  "
          f"resp {(sm.get('HttpResponseTime') or {}).get('peak')}s "
          f"(spike {(sm.get('HttpResponseTime') or {}).get('spike')}s)")

    q_ = d['sql']
    m = q_['metrics']
    print(f"4 SQL   : {q_['tier']}  dtu peak {(m.get('dtu_consumption_percent') or {}).get('peak')}% "
          f"(spike {(m.get('dtu_consumption_percent') or {}).get('spike')}%)  "
          f"storage {(m.get('storage_percent') or {}).get('peak')}%  "
          f"failed-conn {(m.get('connection_failed') or {}).get('total')}  "
          f"deadlocks {(m.get('deadlock') or {}).get('total')}")

    f = d['failures']
    print(f"5 Fails : {f.get('total')} requests, {f.get('failures')} failed ({f.get('pct')}%)  "
          f"| {len(f.get('endpoints', []))} endpoint(s) >={f.get('fail_pct')}%")
    for e in f.get('endpoints', [])[:6]:
        print(f"          {e['Endpoint'][:56]:<56} {e['Failures']}/{e['Total']} {e['FailPct']}%")
    for role in ('api', 'mobile'):
        for e in f.get(f'exceptions_{role}', [])[:3]:
            print(f"          {role.upper():<6} {e['Type'][:48]:<48} {e['Count']}")

    al = d['alerts']
    print(f"6 Alerts: {len(al['fired'])} fired, {al['unacknowledged']} unacknowledged, "
          f"{al['still_firing']} still firing")

    if a.no_save:
        return
    os.makedirs(a.out, exist_ok=True)
    stem = f"TH-monitoring_{(win.get('end_local') or win['end'])[:10]}_{shift or a.window}"
    io.open(os.path.join(a.out, stem + '.html'), 'w', encoding='utf-8').write(render.render(d))
    json.dump(d, io.open(os.path.join(a.out, stem + '.json'), 'w', encoding='utf-8'),
              indent=1, default=str)
    print(f"\nsaved   : {os.path.join(a.out, stem + '.html')}")


if __name__ == '__main__':
    main()
