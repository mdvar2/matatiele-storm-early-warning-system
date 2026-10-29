"""Measure how often the scheduled storm check actually ran (read-only research metric).

Coverage is measured from GitHub Actions workflow-run metadata, never from SMS or
the duplicate-prevention ledger. It reads saved runs-API JSON files, or fetches
them read-only (GET only) with --fetch.

Definitions (UTC):
  hourly slot        one clock hour [HH:00, HH+1:00) inside the measurement window
  slot coverage      share of slots in which at least one run of the workflow started
  success coverage   share of slots with a started run that concluded "success"
  75-minute freshness  share of hour boundaries (HH:00) at which the most recent run
                     started no more than 75 minutes earlier, i.e. a next-hour prediction
                     made by the previous hour's run was still current
  gaps               minutes between consecutive run starts

Trigger groups: event "schedule" = GitHub cron; event "workflow_dispatch" = manual
OR external scheduler (the runs API does not expose dispatch inputs; separate them
with the trigger_source field in run records or Healthchecks HB-1 payloads).

Usage:
  python 21_measure_execution_coverage.py --runs-json runs_p1.json [more.json ...]
  python 21_measure_execution_coverage.py --fetch [--since 2026-11-01T00:00:00Z]
Options: --events schedule,workflow_dispatch  --start/--end ISO-UTC  --json
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from statistics import median

WORKFLOW_PATH = '.github/workflows/scheduled-storm-sms.yml'
FRESHNESS_MINUTES = 75
HOUR = timedelta(hours=1)


def parse_time(text):
    return datetime.strptime(text, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


def load_runs(paths):
    runs = {}
    for path in paths:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
        rows = data.get('workflow_runs', []) if isinstance(data, dict) else data
        for row in rows:
            runs[row['id']] = row  # de-duplicate overlapping pages
    return list(runs.values())


def fetch_runs(repo, token=None, since=None, max_pages=20):
    """Read-only GET of this workflow's runs. Never modifies anything."""
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo or ''):
        raise ValueError('GITHUB_REPOSITORY must look like owner/name')
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
               'User-Agent': 'matatiele-coverage'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    query = f'&created=%3E%3D{since}' if since else ''
    rows = []
    for page in range(1, max_pages + 1):
        url = (f'https://api.github.com/repos/{repo}/actions/workflows/scheduled-storm-sms.yml/runs'
               f'?per_page=100&page={page}{query}')
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
            batch = json.loads(response.read().decode('utf-8')).get('workflow_runs', [])
        rows += batch
        if len(batch) < 100:
            break
    return rows


def run_start(row):
    return parse_time(row.get('run_started_at') or row['created_at'])


def measure(runs, events=('schedule',), start=None, end=None):
    """Return coverage metrics for runs of the production workflow with the given events."""
    selected = sorted((r for r in runs if r.get('event') in events
                       and (r.get('path') or WORKFLOW_PATH).split('@')[0] == WORKFLOW_PATH),
                      key=run_start)
    starts = [run_start(r) for r in selected]
    if not starts and (start is None or end is None):
        return {'events': list(events), 'runs': 0, 'slots': 0, 'error': 'no runs in selection'}
    first_slot = (start or starts[0]).replace(minute=0, second=0, microsecond=0)
    last_slot = (end or starts[-1]).replace(minute=0, second=0, microsecond=0)
    slots = int((last_slot - first_slot) / HOUR) + 1
    in_window = [(t, r) for t, r in zip(starts, selected) if first_slot <= t < last_slot + HOUR]
    covered = {t.replace(minute=0, second=0, microsecond=0) for t, _ in in_window}
    covered_ok = {t.replace(minute=0, second=0, microsecond=0) for t, r in in_window if r.get('conclusion') == 'success'}

    # Freshness at each hour boundary after the first slot: was the last run start within 75 min?
    times = [t for t, _ in in_window]
    fresh, boundaries, i, latest = 0, 0, 0, None
    boundary = first_slot + HOUR
    while boundary <= last_slot:
        while i < len(times) and times[i] <= boundary:
            latest, i = times[i], i + 1
        boundaries += 1
        if latest is not None and boundary - latest <= timedelta(minutes=FRESHNESS_MINUTES):
            fresh += 1
        boundary += HOUR

    gaps = [(b - a).total_seconds() / 60 for a, b in zip(times, times[1:])]
    delays = [(t - t.replace(minute=0, second=0, microsecond=0)).total_seconds() / 60 for t in times]
    return {
        'events': list(events),
        'window_start_slot': first_slot.isoformat(), 'window_end_slot': last_slot.isoformat(),
        'slots': slots, 'runs': len(in_window),
        'covered_slots': len(covered), 'slot_coverage': round(len(covered) / slots, 4),
        'run_to_slot_ratio': round(len(in_window) / slots, 4),
        'success_slots': len(covered_ok), 'success_coverage': round(len(covered_ok) / slots, 4),
        'freshness_boundaries': boundaries,
        'freshness_75min': round(fresh / boundaries, 4) if boundaries else None,
        'gap_minutes_median': round(median(gaps), 1) if gaps else None,
        'gap_minutes_max': round(max(gaps), 1) if gaps else None,
        'gaps_over_75min': sum(g > FRESHNESS_MINUTES for g in gaps),
        'start_minute_median': round(median(delays), 1) if delays else None,
        'conclusions': {c: sum(1 for _, r in in_window if r.get('conclusion') == c)
                        for c in sorted({str(r.get('conclusion')) for _, r in in_window})},
    }


def report_text(results):
    lines = []
    for res in results:
        lines.append(f"events={','.join(res['events'])}")
        if res.get('error'):
            lines.append(f"  {res['error']}")
            continue
        lines += [f"  window {res['window_start_slot']} .. {res['window_end_slot']} ({res['slots']} hourly slots)",
                  f"  runs {res['runs']}; covered slots {res['covered_slots']} ({res['slot_coverage']:.1%}); "
                  f"successful slots {res['success_slots']} ({res['success_coverage']:.1%})",
                  f"  75-minute freshness {res['freshness_75min']:.1%} of {res['freshness_boundaries']} hour boundaries"
                  if res['freshness_75min'] is not None else '  75-minute freshness n/a',
                  f"  gaps: median {res['gap_minutes_median']} min, max {res['gap_minutes_max']} min, "
                  f"{res['gaps_over_75min']} over {FRESHNESS_MINUTES} min; start minute median {res['start_minute_median']}",
                  f"  conclusions {res['conclusions']}"]
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--runs-json', nargs='+')
    source.add_argument('--fetch', action='store_true')
    parser.add_argument('--since', help='with --fetch: only runs created at/after this ISO time')
    parser.add_argument('--events', default='schedule;workflow_dispatch;schedule,workflow_dispatch',
                        help='semicolon-separated groups of comma-separated events')
    parser.add_argument('--start'); parser.add_argument('--end')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    runs = (fetch_runs(os.environ.get('GITHUB_REPOSITORY', ''), os.environ.get('GH_TOKEN'), args.since)
            if args.fetch else load_runs(args.runs_json))
    start = parse_time(args.start) if args.start else None
    end = parse_time(args.end) if args.end else None
    results = [measure(runs, tuple(g.split(',')), start, end) for g in args.events.split(';') if g]
    print(json.dumps(results, indent=2) if args.json else report_text(results))
    return 0


if __name__ == '__main__':
    sys.exit(main())
