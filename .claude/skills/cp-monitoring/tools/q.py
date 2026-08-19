#!/usr/bin/env python
"""Ad-hoc KQL runner against any App Insights component in APPS_EU_PROD.

  python q.py --app <name|guid> [--app <name2> ...] --window 24h --query "<KQL>"
  python q.py --app we-prod-pantheon-appins-01 --window 24h --file myquery.kql

Multiple --app values: the first is the query target, the rest ride along as
cross-resource `applications`, matching workbook cross-component behaviour.
"""
import argparse, io, json, re, shutil, subprocess, sys, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

import cyclewin

API = 'https://api.applicationinsights.io'
AZ = shutil.which('az') or r'C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd'

APPIDS = {
    'we-prod-pantheon-appins-01':     '5814a844-d738-47b9-aabb-a0d5d42b385a',
    'we-prod-pantheon-appins-api-01': '41e51676-7ae1-40e5-a906-013fb29c55f7',
    'we-prod-pantheon-appins-mcp-01': '8dad6f29-e92d-4772-897f-5510d5603008',
    'we-prod-proton-appins-proton':   '03a1148f-52cd-470d-b3d3-edbaa8a5c70d',
    'Proton-Prod':                    '749b8681-1baf-4acf-9133-b30ed9f0b445',
    'we-teamhub-prod-insights-1':     '6e848f1e-195e-41f0-abcc-78b54c0883f3',
}
_TOK = None


def token():
    global _TOK
    if _TOK is None:
        p = subprocess.run([AZ, 'account', 'get-access-token', '--resource', API,
                            '--query', 'accessToken', '-o', 'tsv'],
                           capture_output=True, text=True)
        if p.returncode:
            raise SystemExit('token failed: ' + (p.stderr or p.stdout)[:300])
        _TOK = p.stdout.strip()
    return _TOK


def parse_window(w):
    m = re.fullmatch(r'(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?', w.strip().lower())
    if not m or not any(m.groups()):
        raise SystemExit(f'bad --window {w!r}')
    d, h, mi = (int(x) if x else 0 for x in m.groups())
    return timedelta(days=d, hours=h, minutes=mi)


def query(kql, apps, span):
    ids = [APPIDS.get(a, a) for a in apps]
    body = {'query': kql, 'timespan': span}
    if len(ids) > 1:
        body['applications'] = ids[1:]
    req = urllib.request.Request(
        f'{API}/v1/apps/{ids[0]}/query', data=json.dumps(body).encode(),
        headers={'Authorization': 'Bearer ' + token(), 'Content-Type': 'application/json'},
        method='POST')
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        d = e.read().decode(errors='replace')
        try:
            j = json.loads(d)['error']
            d = f"{j.get('code')}: {j.get('message')}"
        except Exception:
            d = d[:400]
        return None, f'HTTP {e.code} {d}'
    except Exception as e:
        return None, f'{type(e).__name__}: {e}'


def render(tbl, limit):
    cols = [c['name'] for c in tbl['columns']]
    rows = tbl['rows']
    if not rows:
        print('  (no rows)')
        return
    shown = rows[:limit]
    cell = lambda v: '' if v is None else str(v)
    w = [max(len(c), *(len(cell(r[i])) for r in shown)) for i, c in enumerate(cols)]
    print('  ' + '  '.join(c.ljust(w[i]) for i, c in enumerate(cols)))
    print('  ' + '  '.join('-' * x for x in w))
    for r in shown:
        print('  ' + '  '.join(cell(r[i]).ljust(w[i]) for i in range(len(cols))))
    if len(rows) > limit:
        print(f'  ... {len(rows)-limit} more rows')
    print(f'  [{len(rows)} row(s)]')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app', action='append', required=True)
    ap.add_argument('--window', default=None,
                    help='ad hoc override; default is the pinned cycle window')
    ap.add_argument('--query')
    ap.add_argument('--file')
    ap.add_argument('--limit', type=int, default=40)
    a = ap.parse_args()

    kql = a.query or io.open(a.file, encoding='utf-8').read()
    start, end, grain, span, label, pinned = cyclewin.resolve(a.window)

    print(f'APP    : {", ".join(a.app)}')
    print(f'WINDOW : {label}')
    print(f'         {start:%Y-%m-%d %H:%M:%S} -> {end:%Y-%m-%d %H:%M:%S} UTC')
    print('-' * 78)
    res, err = query(kql, a.app, span)
    if err:
        print('ERROR:', err)
        sys.exit(1)
    for t in res.get('tables', []):
        render(t, a.limit)


if __name__ == '__main__':
    main()
