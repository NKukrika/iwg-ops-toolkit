#!/usr/bin/env python
"""ARM helpers — bearer token plus metric fetch.

Calls ARM directly rather than through `az rest`: on Windows `az` is a .cmd shim
routed via cmd.exe, which eats the `&` in a query string.
"""
import json, shutil, subprocess, urllib.error, urllib.parse, urllib.request
from collections import defaultdict

ARM = 'https://management.azure.com'
AZ = shutil.which('az') or r'C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd'
_TOK = {}


def token(resource=ARM):
    if resource not in _TOK:
        p = subprocess.run([AZ, 'account', 'get-access-token', '--resource', resource,
                            '--query', 'accessToken', '-o', 'tsv'],
                           capture_output=True, text=True)
        if p.returncode:
            raise SystemExit('token failed: ' + (p.stderr or p.stdout)[:300])
        _TOK[resource] = p.stdout.strip()
    return _TOK[resource]


def get(url, resource=ARM, timeout=120):
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token(resource)})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
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


def metric(resource_id, names, aggs, span, interval='PT5M', split_instance=False):
    q = {'api-version': '2018-01-01', 'metricnames': names,
         'aggregation': aggs, 'timespan': span, 'interval': interval}
    if split_instance:
        q['$filter'] = "Instance eq '*'"
    return get(f'{ARM}{resource_id}/providers/microsoft.insights/metrics?{urllib.parse.urlencode(q)}')


def by_instance(payload, key='average'):
    """Per-instance series. The dimension is `Instance`, capital I — a lowercase
    comparison silently collapses every instance into one bucket."""
    per = defaultdict(list)
    for m in (payload or {}).get('value', []):
        for ts in m.get('timeseries', []):
            inst = next((mv['value'] for mv in ts.get('metadatavalues', [])
                         if mv['name']['value'].lower() == 'instance'), '(all)')
            for pt in ts.get('data', []):
                if pt.get(key) is not None:
                    per[inst].append((pt['timeStamp'], pt[key]))
    return per


def flat(payload, key):
    """All datapoints for a single metric, ignoring dimensions."""
    return [(pt['timeStamp'], pt[key])
            for m in (payload or {}).get('value', [])
            for ts in m.get('timeseries', [])
            for pt in ts.get('data', []) if pt.get(key) is not None]
