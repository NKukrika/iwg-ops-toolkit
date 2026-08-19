#!/usr/bin/env python
"""Execute Sales Availability & Performance workbook tiles against prod App Insights.

Usage:
  python run_kpi.py --section "Customer Portal"            # default 24h window
  python run_kpi.py --section "Customer Portal" --window 7d
  python run_kpi.py --section Teamhub --window 4h
"""
import argparse, io, json, os, re, shutil, subprocess, sys
from datetime import datetime, timedelta, timezone

import cyclewin

# Resolve relative to this file, not the working directory, so the pipeline
# runs correctly no matter where it is invoked from.
WB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workbook.json')
# On Windows az is a .cmd shim, so shell=False needs the resolved path.
AZ = shutil.which('az') or shutil.which('az.cmd') or \
     r'C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd'


def parse_window(w):
    m = re.fullmatch(r'(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?', w.strip().lower())
    if not m or not any(m.groups()):
        raise SystemExit(f"bad --window {w!r}; use forms like 24h, 7d, 4h30m")
    d, h, mi = (int(x) if x else 0 for x in m.groups())
    return timedelta(days=d, hours=h, minutes=mi)


def grain_for(delta):
    hrs = delta.total_seconds() / 3600
    if hrs <= 6:   return '5m'
    if hrs <= 48:  return '1h'
    if hrs <= 24 * 14: return '6h'
    return '1d'


def timespan_for(start, end):
    """ISO 8601 interval, so the API window matches the substituted datetimes exactly."""
    f = '%Y-%m-%dT%H:%M:%SZ'
    return f'{start.strftime(f)}/{end.strftime(f)}'


def load_tiles(section):
    wb = json.load(io.open(WB, encoding='utf-8-sig'))
    data = json.loads(wb['properties']['serializedData'])
    out = []

    def walk(items, sect=None):
        for it in items or []:
            t, c = it.get('type'), it.get('content', {}) or {}
            if t == 12:
                walk(c.get('items'), c.get('title') or it.get('name') or sect)
            elif t == 3 and sect == section:
                out.append({
                    'name': it.get('name'),
                    'query': c.get('query') or '',
                    'vis': c.get('visualization') or 'grid',
                    'resources': [r.split('/')[-1] for r in (c.get('crossComponentResources') or [])],
                })
    walk(data.get('items'))
    return out


def substitute(q, start, end, grain):
    iso = lambda dt: dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    q = q.replace('{TimeRange:start}', f'datetime({iso(start)})')
    q = q.replace('{TimeRange:end}', f'datetime({iso(end)})')
    q = q.replace('{TimeRange:grain}', grain)
    return q


API = 'https://api.applicationinsights.io'
# Resource name -> appId GUID. Resolved once via `az`, cached to disk.
APPIDS = {
    'we-prod-pantheon-appins-api-01': '41e51676-7ae1-40e5-a906-013fb29c55f7',
    'we-prod-pantheon-appins-mcp-01': '8dad6f29-e92d-4772-897f-5510d5603008',
    'we-prod-proton-appins-proton':   '03a1148f-52cd-470d-b3d3-edbaa8a5c70d',
    'Proton-Prod':                    '749b8681-1baf-4acf-9133-b30ed9f0b445',
    'we-teamhub-prod-insights-1':     '6e848f1e-195e-41f0-abcc-78b54c0883f3',
}
_TOKEN = None


def token():
    global _TOKEN
    if _TOKEN is None:
        p = subprocess.run([AZ, 'account', 'get-access-token', '--resource', API,
                            '--query', 'accessToken', '-o', 'tsv'],
                           capture_output=True, text=True)
        if p.returncode != 0:
            raise SystemExit('token failed: ' + (p.stderr or p.stdout)[:300])
        _TOKEN = p.stdout.strip()
    return _TOKEN


def run(query, apps, timespan):
    """POST to the App Insights query API. Extra apps ride along via `applications`."""
    import urllib.request, urllib.error
    ids = [APPIDS.get(a, a) for a in apps]
    if not ids:
        return None, 'tile has no resource bound'
    body = {'query': query, 'timespan': timespan}
    if len(ids) > 1:
        body['applications'] = ids[1:]
    req = urllib.request.Request(
        f'{API}/v1/apps/{ids[0]}/query',
        data=json.dumps(body).encode(),
        headers={'Authorization': 'Bearer ' + token(),
                 'Content-Type': 'application/json'},
        method='POST')
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors='replace')
        try:
            j = json.loads(detail)['error']
            detail = f"{j.get('code')}: {j.get('message')}"
            inner = j.get('innererror') or {}
            while inner:
                detail += f" | {inner.get('code')}: {inner.get('message')}"
                inner = inner.get('innererror') or {}
        except Exception:
            detail = detail[:400]
        return None, f'HTTP {e.code} {detail}'
    except Exception as e:
        return None, f'{type(e).__name__}: {e}'


def render(tbl):
    cols = [c['name'] for c in tbl['columns']]
    rows = tbl['rows']
    if not rows:
        return '    (no rows)'
    # Tile visualisations are single-row KPI cards; render those as key: value.
    if len(rows) == 1:
        return '\n'.join(f'    {c:<28} {v}' for c, v in zip(cols, rows[0]))
    w = [max(len(str(c)), *(len(str(r[i])) for r in rows)) for i, c in enumerate(cols)]
    head = '  '.join(str(c).ljust(w[i]) for i, c in enumerate(cols))
    sep = '  '.join('-' * x for x in w)
    body = '\n'.join('  '.join(str(r[i]).ljust(w[i]) for i in range(len(cols))) for r in rows[:25])
    extra = f'\n    ... {len(rows) - 25} more rows' if len(rows) > 25 else ''
    return f'    {head}\n    {sep}\n' + '\n'.join('    ' + b for b in body.split('\n')) + extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--section', required=True)
    ap.add_argument('--window', default=None,
                    help='ad hoc override; default is the pinned cycle window')
    ap.add_argument('--only', type=int, nargs='*', help='tile indices to run')
    a = ap.parse_args()

    start, end, grain, span, label, pinned = cyclewin.resolve(a.window)

    tiles = load_tiles(a.section)
    print(f"SECTION : {a.section}")
    print(f"WINDOW  : {label}")
    print(f"          {start:%Y-%m-%d %H:%M:%S} -> {end:%Y-%m-%d %H:%M:%S} UTC, grain {grain}")
    print(f"TILES   : {len(tiles)}")
    print('=' * 78)

    ok = fail = 0
    for i, t in enumerate(tiles):
        if a.only and i not in a.only:
            continue
        if not t['query'].strip():
            continue
        print(f"\n[{i}] {t['vis']}  <- {', '.join(t['resources'])}")
        res, err = run(substitute(t['query'], start, end, grain), t['resources'], span)
        if err:
            fail += 1
            print(f"    ERROR: {err}")
            continue
        ok += 1
        for tbl in res.get('tables', []):
            print(render(tbl))
    print('\n' + '=' * 78)
    print(f"executed {ok} tile(s), {fail} error(s)")


if __name__ == '__main__':
    main()
