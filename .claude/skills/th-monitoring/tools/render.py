#!/usr/bin/env python
"""Render collected TeamHub monitoring data as a standalone HTML report."""
import html, io, os

HERE = os.path.dirname(os.path.abspath(__file__))
PILL = {'ok': 'Ok', 'warn': 'Warn', 'crit': 'Critical', 'none': 'No data'}


def esc(v):
    return html.escape('' if v is None else str(v))


def num(v, suffix='', dash='&mdash;'):
    if v is None:
        return dash
    if isinstance(v, float):
        v = f'{v:,.4f}'.rstrip('0').rstrip('.') if v % 1 else f'{int(v):,}'
    elif isinstance(v, int):
        v = f'{v:,}'
    return f'{v}{suffix}'


def gb(v):
    return '&mdash;' if v is None else f'{v/1_000_000_000:.2f}&thinsp;GB'


def pill(b, colour=False):
    return f'<span class="pill {"p-"+b if colour else "p-plain"}">{PILL.get(b, b)}</span>'


def table(headers, body, caption=None):
    head = ''.join(f'<th{" class=\"num\"" if n else ""}>{h}</th>' for h, n in headers)
    cap = f'<caption>{esc(caption)}</caption>' if caption else ''
    return (f'<div class="scroll"><table>{cap}<thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def section(n, title, note, *blocks):
    return (f'<section><div class="sec-head"><span class="sec-num">{n}</span>'
            f'<h2>{title}</h2><span class="sec-note">{note}</span></div>'
            f'{"".join(blocks)}</section>')


def note(label, *paras):
    return (f'<div class="note"><span class="note-label">{label}</span>'
            + ''.join(f'<p>{p}</p>' for p in paras) + '</div>')


def render(d):
    w, k = d['window'], d['kpis']
    tally = {b: sum(1 for x in k if x['band'] == b) for b in ('ok', 'warn', 'crit', 'none')}

    # 01 KPI availability -- the only section carrying severity colour
    s1 = section('01', 'KPI Availability', '&ge;99.9 ok &middot; &lt;99.9 warn &middot; &lt;99.0 critical',
        table([('KPI', 0), ('Availability', 1), ('Requests', 1), ('Failed', 1), ('Band', 0)],
              [f'<tr><td>{esc(x["name"])}</td><td class="num">{num(x.get("avail"), "%")}</td>'
               f'<td class="num">{num(x.get("requests"))}</td><td class="num">{num(x.get("failed"))}</td>'
               f'<td>{pill(x["band"], colour=True)}</td></tr>' for x in k]),
        '<p class="tally">' + ''.join(f'<span class="pill p-{b}">{tally[b]} {PILL[b].lower()}</span>'
                                      for b in ('ok', 'warn', 'crit', 'none') if tally[b]) + '</p>')

    # 02 availability tests
    a = d['availability']
    if a.get('error'):
        s2body = note('No data', esc(a['error']))
    else:
        s2body = table([('Test', 0), ('Availability', 1), ('Runs', 1), ('Failed', 1), ('Avg ms', 1)],
                       [f'<tr><td class="mono">{esc(t["Test"])}</td>'
                        f'<td class="num">{num(t["Avail"], "%")}</td>'
                        f'<td class="num">{num(t["Runs"])}</td><td class="num">{num(t["Failed"])}</td>'
                        f'<td class="num">{num(t["AvgMs"])}</td></tr>' for t in a.get('tests', [])])
    s2 = section('02', 'Availability Tests',
                 f'{a.get("tests_ok", 0)} of {a.get("tests_total", 0)} clean &middot; '
                 f'{num(a.get("runs"))} runs &middot; 7 locations', s2body)

    # 03 app service
    s = d['appservice']
    pm, sm = s['plan_metrics'], s['site_metrics']
    plan_rows = [f'<tr><td><code>{esc(s["plan"])}</code></td>'
                 f'<td class="num">{s.get("instances", "&mdash;")}</td>'
                 f'<td class="num">{num((pm.get("CpuPercentage") or {}).get("mean"), "%")} / '
                 f'{num((pm.get("CpuPercentage") or {}).get("peak"), "%")}</td>'
                 f'<td class="num">{num((pm.get("MemoryPercentage") or {}).get("mean"), "%")} / '
                 f'<strong>{num((pm.get("MemoryPercentage") or {}).get("peak"), "%")}</strong></td>'
                 f'<td class="num">{num((pm.get("MemoryPercentage") or {}).get("headroom"), " pts")}</td></tr>']
    rt, mw, h5 = sm.get('HttpResponseTime', {}), sm.get('AverageMemoryWorkingSet', {}), sm.get('Http5xx', {})
    site_rows = [f'<tr><td><code>{esc(s["site"])}</code></td>'
                 f'<td class="num">{num(h5.get("total"))}</td>'
                 f'<td class="num">{num(rt.get("mean"), "s")} / {num(rt.get("peak"), "s")}</td>'
                 f'<td class="num">{num(rt.get("spike"), "s")}</td>'
                 f'<td class="num">{gb(mw.get("peak"))}</td></tr>']
    s3 = section('03', 'App Service', 'CPU &gt;90% &middot; memory &gt;90% &middot; 5xx &gt;200 &middot; response &gt;6s',
        table([('Plan', 0), ('Inst', 1), ('CPU mean / peak', 1),
               ('Memory mean / peak', 1), ('Headroom', 1)], plan_rows),
        table([('Site', 0), ('5xx total', 1), ('Response mean / peak', 1),
               ('Momentary spike', 1), ('Working set peak', 1)], site_rows, caption='Site'),
        note('No health probe configured',
             f'<code>{esc(s["site"])}</code> has no <code>healthCheckPath</code> and '
             '<code>alwaysOn</code> is false, so no <code>HealthCheckStatus</code> metric exists. '
             'An unhealthy instance is not pulled from rotation automatically. On a single-instance '
             'plan there is nowhere to reroute to in any case &mdash; noted as an infra observation, '
             'not actioned here.'))

    # 04 SQL
    sq = d['sql']
    m = sq['metrics']
    def row(key, label, suffix='%'):
        x = m.get(key) or {}
        return (f'<tr><td>{label}</td><td class="num">{num(x.get("mean"), suffix)}</td>'
                f'<td class="num"><strong>{num(x.get("peak"), suffix)}</strong></td>'
                f'<td class="num">{num(x.get("spike"), suffix)}</td>'
                f'<td class="num">{num(x.get("headroom"), " pts")}</td></tr>')
    sql_rows = [row('dtu_consumption_percent', 'DTU consumption'),
                row('cpu_percent', 'CPU'),
                row('storage_percent', 'Storage'),
                row('sessions_percent', 'Sessions')]
    cf, dl = (m.get('connection_failed') or {}), (m.get('deadlock') or {})
    sql_rows.append(f'<tr><td>Failed connections</td><td class="num">&mdash;</td>'
                    f'<td class="num"><strong>{num(cf.get("total"))}</strong></td>'
                    f'<td class="num">&mdash;</td><td class="num">&mdash;</td></tr>')
    sql_rows.append(f'<tr><td>Deadlocks</td><td class="num">&mdash;</td>'
                    f'<td class="num"><strong>{num(dl.get("total"))}</strong></td>'
                    f'<td class="num">&mdash;</td><td class="num">&mdash;</td></tr>')
    s4 = section('04', 'SQL Database', f'{esc(sq["database"])} &middot; {esc(sq["tier"])}',
        table([('Metric', 0), ('Mean', 1), ('Peak', 1), ('Momentary spike', 1), ('Headroom', 1)], sql_rows),
        note('Bands here are our own convention',
             'No Azure alert rules are configured on this database. The bands used '
             '(amber 75%, red 90%) are ours, not Azure config. The database is '
             f'<strong>{esc(sq["tier"])}</strong>, which is small for a production API &mdash; '
             'which is why it is measured every cycle.'))

    # 05 application failures
    f = d['failures']
    if f.get('endpoints'):
        ep = table([('Endpoint', 0), ('Failures', 1), ('Calls', 1), ('Fail %', 1), ('Codes', 1)],
                   [f'<tr><td class="mono">{esc(e["Endpoint"])}</td>'
                    f'<td class="num"><strong>{num(e["Failures"])}</strong></td>'
                    f'<td class="num">{num(e["Total"])}</td>'
                    f'<td class="num">{num(e["FailPct"], "%")}</td>'
                    f'<td class="num">{esc(", ".join(e.get("Codes") or []))}</td></tr>'
                    for e in f['endpoints']])
    else:
        ep = note('Clear', f'No endpoint failed at or above {f.get("fail_pct")}% '
                           f'over {f.get("min_calls")} calls.')
    exc_rows = []
    for role in ('api', 'mobile'):
        for e in f.get(f'exceptions_{role}', []):
            exc_rows.append(f'<tr><td>{role.upper()}</td><td class="mono">{esc(e["Type"])}</td>'
                            f'<td class="mono">{esc(e.get("Method") or "")}</td>'
                            f'<td class="num">{num(e["Count"])}</td></tr>')
    exc = (table([('Component', 0), ('Exception type', 0), ('Method', 0), ('Count', 1)],
                 exc_rows, caption=f'Exception types at or above {f.get("exception_min")}')
           if exc_rows else
           note('Clear', f'No exception type reached {f.get("exception_min")} occurrences.'))
    s5 = section('05', 'Application Failures',
                 f'{num(f.get("total"))} requests &middot; {num(f.get("failures"))} failed '
                 f'&middot; {num(f.get("pct"), "%")}',
                 f'<p>TeamHub&rsquo;s own endpoints and exceptions. Rate-based with a volume floor '
                 f'rather than a fixed failure count, because traffic swings roughly 20&times; '
                 f'between weekday and weekend.</p>', ep, exc)

    # 06 alerts
    al = d['alerts']
    cr = [f'<tr><td>{c["role"]} <code>{esc(c["component"])}</code></td>'
          f'<td class="num">{c.get("fired", esc(c.get("error", "&mdash;")))}</td></tr>'
          for c in al['components']]
    ft = (table([('Rule', 0), ('Sev', 1), ('State', 1), ('Fired', 1), ('Resolved', 1)],
                [f'<tr><td class="mono">{esc(x["rule"])}</td><td class="num">{esc(x["sev"])}</td>'
                 f'<td class="num">{esc(x["state"])}</td><td class="num">{esc(x["fired"])}</td>'
                 f'<td class="num">{esc(x["resolved"]) or "still firing"}</td></tr>' for x in al['fired']],
                caption='Fired in window')
          if al['fired'] else
          note('Clear', 'No alerts fired on either component in this window.'))
    s6 = section('06', 'Alerts', f'{len(al["fired"])} fired &middot; {al["unacknowledged"]} unacknowledged',
                 table([('Component', 0), ('Fired', 1)], cr), ft)

    # needs attention -- derived from the data
    att = []
    for x in k:
        if x['band'] in ('warn', 'crit'):
            att.append(f'KPI <strong>{esc(x["name"])}</strong> at {num(x.get("avail"), "%")} '
                       f'({num(x.get("failed"))} failed of {num(x.get("requests"))})')
    if a.get('avail') is not None and a['avail'] < 100:
        att.append(f'Availability {num(a["avail"], "%")} &mdash; '
                   f'{a.get("tests_total", 0) - a.get("tests_ok", 0)} test(s) failing')
    for n_, mm in list(pm.items()) + list(sm.items()):
        if mm.get('band') in ('warn', 'crit'):
            att.append(f'App Service <strong>{n_}</strong> peaked at {num(mm.get("peak"))}')
    for n_, mm in m.items():
        if mm.get('band') in ('warn', 'crit'):
            att.append(f'SQL <strong>{n_}</strong> peaked at {num(mm.get("peak"), "%")}')
    for e in f.get('endpoints', []):
        att.append(f'Endpoint <code>{esc(e["Endpoint"])}</code> &mdash; {num(e["Failures"])} '
                   f'failures at {num(e["FailPct"], "%")}')
    for x in al['fired']:
        if x['condition'] == 'Fired':
            att.append(f'Alert <strong>{esc(x["rule"])}</strong> still firing')
        elif x['state'] == 'New':
            att.append(f'Alert <strong>{esc(x["rule"])}</strong> fired and resolved unacknowledged')
    s7 = section('&mdash;', 'Needs Attention', f'{len(att)} item(s)',
                 (f'<ul>{"".join(f"<li>{x}</li>" for x in att)}</ul>' if att else
                  note('Clear', 'Nothing in this window breached a configured threshold.')))

    strip = [('01', 'KPI availability', f'{tally["ok"]} ok &middot; {tally["warn"]+tally["crit"]} flagged'),
             ('02', 'Availability tests', num(a.get('avail'), '%')),
             ('03', 'App Service', num((pm.get('MemoryPercentage') or {}).get('peak'), '% mem')),
             ('04', 'SQL database', num((m.get('dtu_consumption_percent') or {}).get('peak'), '% DTU')),
             ('05', 'App failures', f'{len(f.get("endpoints", []))} endpoint(s)'),
             ('06', 'Alerts', f'{len(al["fired"])} fired')]
    strip_html = ''.join(f'<div class="chk"><span class="chk-n">{n}</span>'
                         f'<span class="chk-name">{t}</span>'
                         f'<span class="chk-state">{v}</span></div>' for n, t, v in strip)

    css = io.open(os.path.join(HERE, 'report.css'), encoding='utf-8').read()
    shift = w.get('label') or 'Cycle'

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TeamHub monitoring &mdash; {esc(shift)} {esc((w.get('end_local') or w.get('end') or '')[:10])}</title>
<style>{css}</style></head><body>
<div class="wrap">
  <header class="masthead">
    <p class="eyebrow">IWG &middot; TeamHub Production &middot; {esc(shift)} run</p>
    <h1>TeamHub monitoring</h1>
    <p class="standfirst">Six-step production sweep across KPI availability, synthetic
      availability tests, App Service, the SQL database, application failures and fired
      alerts. Every step reports on the same pinned window.</p>
    <dl class="meta">
      <div><dt>Window (UTC)</dt><dd>{esc(w.get('start'))} &rarr; {esc(w.get('end'))}</dd></div>
      <div><dt>Span</dt><dd>{esc(shift)}{(' &middot; ' + str(w.get('span_h')) + 'h') if w.get('span_h') else ''}</dd></div>
      <div><dt>Generated</dt><dd>{esc(w.get('pinned_at'))}</dd></div>
      <div><dt>Subscription</dt><dd>APPS_EU_PROD</dd></div>
    </dl>
  </header>
  <section aria-label="Cycle overview"><div class="cycle">{strip_html}</div></section>
  {s1}{s2}{s3}{s4}{s5}{s6}{s7}
  <footer>
    Method &mdash; all six steps read one pinned window, so figures are directly comparable.
    KPI bands come from the workbook tile config; App Service bands from the configured Azure
    alert rules; SQL bands are our own convention, as no alert rules exist on that database.
    Everything is banded on the highest 5-minute <em>average</em>, never the maximum &mdash;
    momentary spikes are reported separately and are not threshold breaches.
    <code>success</code> is a string whose values differ per table:
    <code>"1"</code>/<code>"0"</code> in availabilityResults, <code>"True"</code>/<code>"False"</code>
    in requests. Scope is TeamHub only; downstream Proton health belongs to the Customer
    Portal cycle.
  </footer>
</div></body></html>"""


if __name__ == '__main__':
    import json, sys
    print(render(json.load(io.open(sys.argv[1], encoding='utf-8'))))
