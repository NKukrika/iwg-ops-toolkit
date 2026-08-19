#!/usr/bin/env python
"""Render collected monitoring data as a standalone HTML report.

Shares report.css with the published artifact so the saved files and the
shareable page stay one design. Severity colour appears in section 01 only,
where the workbook itself defines the RAG bands.
"""
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


def pill(bandname, colour=False):
    cls = f'p-{bandname}' if colour else 'p-plain'
    return f'<span class="pill {cls}">{PILL.get(bandname, bandname)}</span>'


def table(headers, body_rows, caption=None):
    head = ''.join(f'<th{" class=\"num\"" if n else ""}>{h}</th>' for h, n in headers)
    cap = f'<caption>{esc(caption)}</caption>' if caption else ''
    return (f'<div class="scroll"><table>{cap}<thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body_rows)}</tbody></table></div>')


def section(n, title, note, *blocks):
    return (f'<section><div class="sec-head"><span class="sec-num">{n}</span>'
            f'<h2>{title}</h2><span class="sec-note">{note}</span></div>'
            f'{"".join(blocks)}</section>')


def render(d):
    w = d['window']
    k = d['kpis']
    tally = {b: sum(1 for x in k if x['band'] == b) for b in ('ok', 'warn', 'crit', 'none')}

    # ---- 01 KPI availability (the one section that keeps severity colour)
    kpi_rows = [
        f'<tr><td>{esc(x["name"])}</td><td class="num">{num(x.get("avail"), "%")}</td>'
        f'<td class="num">{num(x.get("requests"))}</td><td class="num">{num(x.get("failed"))}</td>'
        f'<td>{pill(x["band"], colour=True)}</td></tr>' for x in k]
    s1 = section('01', 'KPI Availability', '&ge;99.9 ok &middot; &lt;99.9 warn &middot; &lt;99.0 critical',
                 table([('KPI', 0), ('Availability', 1), ('Requests', 1), ('Failed', 1), ('Band', 0)], kpi_rows),
                 '<p class="tally">'
                 + ''.join(f'<span class="pill p-{b}">{tally[b]} {PILL[b].lower()}</span>'
                           for b in ('ok', 'warn', 'crit', 'none') if tally[b])
                 + '</p>')

    # ---- 02 availability tests
    av_rows = []
    for a in d['availability']:
        if a.get('error'):
            av_rows.append(f'<tr><td>{a["role"]} <code>{esc(a["component"])}</code></td>'
                           f'<td class="num" colspan="4">{esc(a["error"])}</td></tr>')
            continue
        av_rows.append(
            f'<tr><td>{a["role"]} <code>{esc(a["component"])}</code></td>'
            f'<td class="num">{num(a["avail"], "%")}</td><td class="num">{num(a["runs"])}</td>'
            f'<td class="num">{num(a["failed"])}</td>'
            f'<td class="num">{a["tests_ok"]} of {a["tests_total"]}</td></tr>')
    worst = [t for a in d['availability'] for t in a.get('worst', [])]
    s2_extra = ''
    if worst:
        rows_ = [f'<tr><td class="mono">{esc(t["Test"])}</td><td class="num">{num(t["Avail"], "%")}</td>'
                 f'<td class="num">{num(t["Runs"])}</td><td class="num">{num(t["Failed"])}</td></tr>'
                 for t in sorted(worst, key=lambda x: x['Avail'])]
        s2_extra = table([('Failing test', 0), ('Availability', 1), ('Runs', 1), ('Failed', 1)],
                         rows_, caption='Tests below 100%')
    s2 = section('02', 'Web &amp; API Availability', 'Synthetic tests &middot; 7 locations',
                 table([('Instance', 0), ('Availability', 1), ('Runs', 1), ('Failed', 1), ('Tests at 100%', 1)], av_rows),
                 s2_extra)

    # ---- 03 plan resources
    pl_rows = []
    for p in d['plans']:
        cpu, mem = p.get('cpu'), p.get('mem')
        pl_rows.append(
            f'<tr><td>{p["role"]} <code>{esc(p["plan"])}</code></td>'
            f'<td class="num">{p.get("instances", "&mdash;")}</td>'
            f'<td class="num">{num(cpu["mean"], "%") if cpu else "&mdash;"} / '
            f'{num(cpu["peak"], "%") if cpu else "&mdash;"}</td>'
            f'<td class="num">{num(mem["mean"], "%") if mem else "&mdash;"} / '
            f'<strong>{num(mem["peak"], "%") if mem else "&mdash;"}</strong></td>'
            f'<td class="num">{num(p.get("headroom"), " pts")}</td></tr>')
    s3 = section('03', 'App Service Plan Resources', 'Highest 5-min average &middot; alerts at CPU 90% / memory 80%',
                 table([('Plan', 0), ('Inst', 1), ('CPU mean / peak', 1),
                        ('Memory mean / peak', 1), ('Headroom to alert', 1)], pl_rows))

    # ---- 04 health check
    h_rows = []
    for h in d['health']:
        if h.get('error'):
            h_rows.append(f'<tr><td>{h["role"]} <code>{esc(h["site"])}</code></td>'
                          f'<td class="mono">{esc(h["probe"])}</td>'
                          f'<td class="num" colspan="4">{esc(h["error"])}</td></tr>')
            continue
        h_rows.append(
            f'<tr><td>{h["role"]} <code>{esc(h["site"])}</code></td>'
            f'<td class="mono">{esc(h["probe"])}</td>'
            f'<td class="num">{num(h["health"], "%")}</td>'
            f'<td class="num">{h["instances"]}</td><td class="num">{h["degraded"]}</td>'
            f'<td class="num">{h["affected"]} of {h["instances"]}</td></tr>')
    s4 = section('04', 'Health Check', '100 = probe passing',
                 table([('Site', 0), ('Probe', 0), ('Health', 1), ('Inst', 1),
                        ('Degraded', 1), ('Instances affected', 1)], h_rows))

    # ---- 05 proton
    pr = d['proton']
    if pr['breaches']:
        pr_rows = [f'<tr><td class="mono">{esc(b["Endpoint"])}</td>'
                   f'<td class="num"><strong>{num(b["Failures"])}</strong></td>'
                   f'<td class="num">{num(b["Total"])}</td><td class="num">{num(b["FailPct"], "%")}</td>'
                   f'<td class="num">{esc(b["code"])}</td><td class="mono">{esc(b["role"])}</td></tr>'
                   for b in pr['breaches']]
        pr_body = table([('Endpoint', 0), ('Failures', 1), ('Total', 1), ('Fail %', 1),
                         ('Code', 1), ('Role', 0)], pr_rows)
    else:
        pr_body = (f'<div class="note"><span class="note-label">Clear</span>'
                   f'<p>No endpoint exceeded {pr["threshold"]:,} failures in this window.</p></div>')
    s5 = section('05', 'Proton API Failure Scan',
                 f'{num(pr["total"])} requests &middot; {num(pr["failures"])} failed &middot; {num(pr["pct"], "%")}',
                 f'<p>Endpoints exceeding the {pr["threshold"]:,}-failure threshold.</p>', pr_body)

    # ---- 06 alerts
    al = d['alerts']
    c_rows = [f'<tr><td>{c["role"]} <code>{esc(c["component"])}</code></td>'
              f'<td class="num">{c.get("fired", esc(c.get("error", "&mdash;")))}</td></tr>'
              for c in al['components']]
    if al['fired']:
        f_rows = [f'<tr><td class="mono">{esc(f["rule"])}</td><td class="num">{esc(f["sev"])}</td>'
                  f'<td class="num">{esc(f["state"])}</td><td class="num">{esc(f["fired"])}</td>'
                  f'<td class="num">{esc(f["resolved"]) or "still firing"}</td></tr>'
                  for f in al['fired']]
        fired_tbl = table([('Rule', 0), ('Sev', 1), ('State', 1), ('Fired', 1), ('Resolved', 1)],
                          f_rows, caption='Fired in window')
    else:
        fired_tbl = ('<div class="note"><span class="note-label">Clear</span>'
                     '<p>No alerts fired on any monitored component in this window.</p></div>')
    s6 = section('06', 'Alerts',
                 f'{len(al["fired"])} fired &middot; {al["unacknowledged"]} unacknowledged',
                 table([('Component', 0), ('Fired', 1)], c_rows), fired_tbl)

    # ---- attention, derived from the data rather than hand-written
    att = []
    for x in k:
        if x['band'] in ('warn', 'crit'):
            att.append(f'KPI <strong>{esc(x["name"])}</strong> at {num(x.get("avail"), "%")} '
                       f'({num(x.get("failed"))} failed of {num(x.get("requests"))})')
    for a in d['availability']:
        if a.get('avail') is not None and a['avail'] < 100:
            att.append(f'{a["role"]} availability {num(a["avail"], "%")} &mdash; '
                       f'{a["tests_total"] - a["tests_ok"]} test(s) failing')
    for p in d['plans']:
        if p.get('headroom') is not None and p['headroom'] < 10:
            att.append(f'{p["role"]} plan memory within {num(p["headroom"], " pts")} of its 80% Sev1 threshold')
    for h in d['health']:
        if h.get('degraded'):
            att.append(f'{h["role"]} health probe degraded in {h["degraded"]} interval(s) '
                       f'across {h["affected"]} instance(s)')
    for b in pr['breaches']:
        att.append(f'Proton <code>{esc(b["Endpoint"])}</code> &mdash; {num(b["Failures"])} failures '
                   f'at {num(b["FailPct"], "%")} (HTTP {esc(b["code"])})')
    for f in al['fired']:
        if f['condition'] == 'Fired':
            att.append(f'Alert <strong>{esc(f["rule"])}</strong> still firing, state {esc(f["state"])}')
        elif f['state'] == 'New':
            att.append(f'Alert <strong>{esc(f["rule"])}</strong> fired and resolved without acknowledgement')
    att_block = (f'<ul>{"".join(f"<li>{a}</li>" for a in att)}</ul>' if att else
                 '<div class="note"><span class="note-label">Clear</span>'
                 '<p>Nothing in this window breached a configured threshold.</p></div>')
    s7 = section('&mdash;', 'Needs Attention', f'{len(att)} item(s)', att_block)

    # ---- cycle strip
    strip = [
        ('01', 'KPI availability', f'{tally["ok"]} ok &middot; {tally["warn"] + tally["crit"]} flagged'),
        ('02', 'Web &amp; API availability',
         ' &middot; '.join(f'{a["role"]} {num(a.get("avail"), "%")}' for a in d['availability'])),
        ('03', 'Plan resources',
         ' &middot; '.join(f'{p["role"]} {num(p["mem"]["peak"], "%")}' for p in d['plans'] if p.get('mem'))),
        ('04', 'Health check',
         ' &middot; '.join(f'{h["role"]} {num(h.get("health"), "%")}' for h in d['health'] if not h.get('error'))),
        ('05', 'Proton failures', f'{len(pr["breaches"])} breach(es)'),
        ('06', 'Alerts', f'{len(al["fired"])} fired'),
    ]
    strip_html = ''.join(
        f'<div class="chk"><span class="chk-n">{n}</span><span class="chk-name">{t}</span>'
        f'<span class="chk-state">{s}</span></div>' for n, t, s in strip)

    css = io.open(os.path.join(HERE, 'report.css'), encoding='utf-8').read()
    shift = w.get('label') or 'Cycle'

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Customer Portal monitoring &mdash; {esc(shift)} {esc((w.get('end_local') or '')[:10])}</title>
<style>{css}</style></head><body>
<div class="wrap">
  <header class="masthead">
    <p class="eyebrow">IWG &middot; Pantheon Production &middot; {esc(shift)} run</p>
    <h1>Customer Portal monitoring</h1>
    <p class="standfirst">Six-step production sweep across KPI availability, synthetic availability
      tests, plan resources, health probes, Proton endpoint failures and fired alerts.
      Every step reports on the same pinned window.</p>
    <dl class="meta">
      <div><dt>Shift</dt><dd>{esc(shift)} &middot; {esc(w.get('span_h'))}h</dd></div>
      <div><dt>Covers (local)</dt><dd>{esc((w.get('start_local') or '')[11:])} &rarr; {esc((w.get('end_local') or '')[11:])}</dd></div>
      <div><dt>Window (UTC)</dt><dd>{esc(w.get('start'))} &rarr; {esc(w.get('end'))}</dd></div>
      <div><dt>Generated</dt><dd>{esc(w.get('pinned_at'))}</dd></div>
    </dl>
  </header>
  <section aria-label="Cycle overview"><div class="cycle">{strip_html}</div></section>
  {s1}{s2}{s3}{s4}{s5}{s6}{s7}
  <footer>
    Method &mdash; all six steps read one pinned window, so figures are directly comparable across sections.
    KPI bands come from the Sales Availability and Performance workbook; resource bands from the Sev1
    metric alerts on each plan. Availability is computed as <code>tostring(success) == "1"</code> on
    availabilityResults and <code>== "True"</code> on Proton requests &mdash; the column is a string and
    its values differ per component.
  </footer>
</div></body></html>"""


if __name__ == '__main__':
    import json, sys
    print(render(json.load(io.open(sys.argv[1], encoding='utf-8'))))
