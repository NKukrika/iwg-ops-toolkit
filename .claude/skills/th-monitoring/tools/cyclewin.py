#!/usr/bin/env python
"""Shared monitoring-cycle window.

One window is pinned per cycle and every step reads it, so step 1 and step N
report on byte-identical time ranges.

  python cyclewin.py new            # pin a fresh 24h window ending now
  python cyclewin.py new --window 7d
  python cyclewin.py new --end 2026-08-14T12:00:00Z --window 24h
  python cyclewin.py show

Steps call resolve(args.window) — an explicit --window on a step overrides the
pin for that one query without disturbing the cycle.
"""
import argparse, io, json, os, re, sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'window.json')
FMT = '%Y-%m-%dT%H:%M:%SZ'

LOCAL = ZoneInfo('Europe/Sarajevo')

# The three daily runs. Each covers the span since the previous run, so the
# three together tile a full day with no gap and no overlap. Local hours are
# resolved through zoneinfo, so the CEST -> CET change in October is handled.
SHIFTS = {
    'morning': {'label': 'Morning',  'run_at': 8,  'from_hour': 22, 'span_h': 10, 'prev_day': True},
    'midday':  {'label': 'Midday',   'run_at': 15, 'from_hour': 8,  'span_h': 7,  'prev_day': False},
    'evening': {'label': 'Evening',  'run_at': 22, 'from_hour': 15, 'span_h': 7,  'prev_day': False},
}


def shift_window(name, on_date=None):
    """Resolve a named shift to (start_utc, end_utc) plus local-time labels."""
    s = SHIFTS.get(name)
    if not s:
        raise SystemExit(f'unknown shift {name!r}; use one of {", ".join(SHIFTS)}')
    today = on_date or datetime.now(LOCAL).date()
    end_local = datetime(today.year, today.month, today.day, s['run_at'], 0, 0, tzinfo=LOCAL)
    start_local = end_local - timedelta(hours=s['span_h'])
    return {
        'shift': name,
        'label': s['label'],
        'start': start_local.astimezone(timezone.utc).strftime(FMT),
        'end': end_local.astimezone(timezone.utc).strftime(FMT),
        'start_local': start_local.strftime('%Y-%m-%d %H:%M %Z'),
        'end_local': end_local.strftime('%Y-%m-%d %H:%M %Z'),
        'span_h': s['span_h'],
        'window': f"{s['span_h']}h",
        'grain': grain_for(timedelta(hours=s['span_h'])),
    }


def current_shift():
    """Whichever shift this moment falls in, by local hour."""
    h = datetime.now(LOCAL).hour
    if 8 <= h < 15:
        return 'midday'
    if 15 <= h < 22:
        return 'evening'
    return 'morning'


def parse_window(w):
    m = re.fullmatch(r'(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?', w.strip().lower())
    if not m or not any(m.groups()):
        raise SystemExit(f'bad window {w!r}; use forms like 24h, 7d, 4h30m')
    d, h, mi = (int(x) if x else 0 for x in m.groups())
    return timedelta(days=d, hours=h, minutes=mi)


def grain_for(delta):
    hrs = delta.total_seconds() / 3600
    if hrs <= 6:        return '5m'
    if hrs <= 48:       return '1h'
    if hrs <= 24 * 14:  return '6h'
    return '1d'


def pin(window='24h', end=None, shift=None, on_date=None):
    if shift:
        data = shift_window(shift, on_date)
    else:
        delta = parse_window(window)
        end_dt = (datetime.strptime(end, FMT).replace(tzinfo=timezone.utc) if end
                  else datetime.now(timezone.utc).replace(microsecond=0))
        start_dt = end_dt - delta
        data = {'window': window,
                'start': start_dt.strftime(FMT),
                'end': end_dt.strftime(FMT),
                'grain': grain_for(delta)}
    data['pinned_at'] = datetime.now(timezone.utc).strftime(FMT)
    json.dump(data, io.open(PIN, 'w', encoding='utf-8'), indent=1)
    return data


def load():
    if not os.path.exists(PIN):
        return None
    return json.load(io.open(PIN, encoding='utf-8'))


def resolve(window_override=None):
    """Return (start, end, grain, span, label, pinned).

    window_override wins; otherwise the pinned cycle window; otherwise 24h.
    """
    if window_override:
        delta = parse_window(window_override)
        end = datetime.now(timezone.utc).replace(microsecond=0)
        start = end - delta
        return (start, end, grain_for(delta),
                f'{start.strftime(FMT)}/{end.strftime(FMT)}',
                f'{window_override} (ad hoc, not the pinned cycle)', False)

    p = load()
    if p is None:
        sys.stderr.write('no pinned window; run: python cyclewin.py new\n')
        d = pin('24h')
        p = d
    start = datetime.strptime(p['start'], FMT).replace(tzinfo=timezone.utc)
    end = datetime.strptime(p['end'], FMT).replace(tzinfo=timezone.utc)
    return (start, end, p['grain'], f"{p['start']}/{p['end']}",
            f"{p['window']} (pinned cycle)", True)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    n = sub.add_parser('new')
    n.add_argument('--window', default='24h')
    n.add_argument('--end', help='UTC end instant as YYYY-MM-DDThh:mm:ssZ; default now')
    n.add_argument('--shift', choices=list(SHIFTS) + ['auto'],
                   help='use a named daily shift instead of a rolling window')
    n.add_argument('--date', help='shift date as YYYY-MM-DD (local); default today')
    sub.add_parser('show')
    sub.add_parser('shifts')
    a = ap.parse_args()

    if a.cmd == 'shifts':
        print(f'daily shifts (local {LOCAL}):\n')
        for name in SHIFTS:
            w = shift_window(name)
            print(f"  {name:<8} runs {SHIFTS[name]['run_at']:02d}:00 local, covers "
                  f"{w['start_local']} -> {w['end_local']}  ({w['span_h']}h)")
            print(f"           UTC {w['start']} -> {w['end']}")
        return

    if a.cmd == 'new':
        shift = current_shift() if a.shift == 'auto' else a.shift
        on_date = datetime.strptime(a.date, '%Y-%m-%d').date() if a.date else None
        d = pin(a.window, a.end, shift, on_date)
        print('pinned cycle window:')
    else:
        d = load()
        if d is None:
            raise SystemExit('no window pinned; run: python cyclewin.py new')
        print('current cycle window:')
    for k in ('shift', 'label', 'window', 'start', 'end', 'start_local', 'end_local', 'grain', 'pinned_at'):
        if k in d:
            print(f'  {k:<12} {d[k]}')


if __name__ == '__main__':
    main()
