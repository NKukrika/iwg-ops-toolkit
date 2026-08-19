#!/usr/bin/env python
"""Run one Customer Portal monitoring shift and save the report to disk.

  python report.py --shift midday
  python report.py --shift auto --out "<output-dir>"
  python report.py --shift morning --date 2026-08-13    # re-run a past shift

Writes two files per run into the output folder:
  CP-monitoring_<date>_<shift>.html   the report
  CP-monitoring_<date>_<shift>.json   the raw collected data
"""
import argparse, io, json, os, sys

import cyclewin, collect, render

DEFAULT_OUT = os.environ.get('CP_REPORT_DIR') or os.path.join(
    os.path.expanduser('~'), 'CP-Monitoring-Reports')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--shift', default='auto',
                    choices=list(cyclewin.SHIFTS) + ['auto'],
                    help='which daily run; auto picks by current local hour')
    ap.add_argument('--date', help='shift date YYYY-MM-DD (local); default today')
    ap.add_argument('--out', default=DEFAULT_OUT, help='output folder')
    ap.add_argument('--no-save', action='store_true', help='print a summary only')
    a = ap.parse_args()

    from datetime import datetime
    shift = cyclewin.current_shift() if a.shift == 'auto' else a.shift
    on_date = datetime.strptime(a.date, '%Y-%m-%d').date() if a.date else None

    win = cyclewin.pin(shift=shift, on_date=on_date)
    print(f"shift   : {win['label']} ({win['span_h']}h)")
    print(f"covers  : {win['start_local']} -> {win['end_local']}")
    print(f"UTC     : {win['start']} -> {win['end']}")

    data = collect.collect()

    # concise console summary so a scheduled run leaves a readable trace
    tally = {}
    for k in data['kpis']:
        tally[k['band']] = tally.get(k['band'], 0) + 1
    print(f"\nKPIs    : " + ', '.join(f'{v} {k}' for k, v in sorted(tally.items())))
    for av in data['availability']:
        print(f"{av['role']:<8}: availability {av.get('avail')}%  "
              f"({av.get('tests_ok')}/{av.get('tests_total')} tests clean)")
    for p in data['plans']:
        if p.get('mem'):
            print(f"{p['role']:<8}: memory peak {p['mem']['peak']}%  headroom {p.get('headroom')} pts")
    for h in data['health']:
        if not h.get('error'):
            print(f"{h['role']:<8}: health {h['health']}%  degraded intervals {h['degraded']}")
    pr = data['proton']
    print(f"Proton  : {len(pr['breaches'])} endpoint(s) over {pr['threshold']:,} failures")
    for b in pr['breaches']:
        print(f"          {b['Endpoint']}  {b['Failures']:,} failures  {b['FailPct']}%")
    al = data['alerts']
    print(f"Alerts  : {len(al['fired'])} fired, {al['unacknowledged']} unacknowledged, "
          f"{al['still_firing']} still firing")

    if a.no_save:
        return

    os.makedirs(a.out, exist_ok=True)
    stem = f"CP-monitoring_{win['end_local'][:10]}_{shift}"
    html_path = os.path.join(a.out, stem + '.html')
    json_path = os.path.join(a.out, stem + '.json')

    io.open(html_path, 'w', encoding='utf-8').write(render.render(data))
    json.dump(data, io.open(json_path, 'w', encoding='utf-8'), indent=1, default=str)

    print(f"\nsaved   : {html_path}")
    print(f"          {json_path}")


if __name__ == '__main__':
    main()
