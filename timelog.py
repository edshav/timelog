#!/usr/bin/env python3
"""Hours from Claude Code transcripts. Spec: docs/design.md.

Usage: timelog.py hook | draft [SINCE] | test
"""
import datetime as dt
import json
import math
import os
import subprocess
import sys
import tempfile
from itertools import groupby
from pathlib import Path

ROOT = Path(os.environ.get('TIMELOG_ROOT') or Path.home() / 'projects')
DATA = Path(os.environ.get('TIMELOG_DATA') or ROOT / 'timelog-data')
CSV = DATA / 'timelog.csv'
MARKER = DATA / '.confirmed'
TRANSCRIPTS = Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude') / 'projects'
GAP = dt.timedelta(minutes=20)


def intervals(stamps):
    """Active intervals of one session: consecutive stamps more than 0 and at most GAP apart."""
    s = sorted(stamps)
    return [(a, b) for a, b in zip(s, s[1:]) if dt.timedelta(0) < b - a <= GAP]


def hours(ivs):
    """Length of the union of intervals, in hours."""
    total, end = dt.timedelta(0), dt.datetime.min
    for a, b in sorted(ivs):
        total += max(b - max(a, end), dt.timedelta(0))
        end = max(end, b)
    return total.total_seconds() / 3600


def report(sessions):
    """{day: (wall, {client: (total, [(session, share)])})}; an interval counts on its start day."""
    days = {}
    for s in sessions:
        for day, ivs in groupby(intervals(s['stamps']), key=lambda iv: iv[0].date()):
            days.setdefault(day, {}).setdefault(s['client'], []).append((s, list(ivs)))
    out = {}
    for day, clients in sorted(days.items()):
        totals = {}
        for client, items in clients.items():
            total = hours([iv for _, ivs in items for iv in ivs])
            own = [hours(ivs) for _, ivs in items]
            totals[client] = (total, [(s, o * total / sum(own)) for (s, _), o in zip(items, own)])
        wall = hours([iv for items in clients.values() for _, ivs in items for iv in ivs])
        out[day] = (wall, totals)
    return out


def collect(start, base=TRANSCRIPTS):
    """Sessions under ROOT, with their timestamps after `start` in local time."""
    cutoff = dt.datetime.combine(start + dt.timedelta(days=1), dt.time()).timestamp()
    sessions = []
    for f in base.glob('*/*.jsonl'):
        if f.stat().st_mtime < cutoff:
            continue
        s = {'cwd': None, 'title': '', 'prompt': '', 'stamps': []}
        with f.open(encoding='utf-8', errors='replace') as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                    stamp = r.get('timestamp')
                    if stamp:
                        stamp = dt.datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                        stamp = stamp.astimezone().replace(tzinfo=None)
                except (ValueError, AttributeError):
                    continue  # not JSON, not an object, or a bad timestamp
                if s['cwd'] is None and r.get('cwd'):
                    s['cwd'] = Path(r['cwd'])
                if r.get('aiTitle'):
                    s['title'] = r['aiTitle']
                content = (r.get('message') or {}).get('content') if r.get('type') == 'user' else None
                if not s['prompt'] and isinstance(content, str) and not content.startswith('<'):
                    s['prompt'] = content
                # away_summary is written ~3 min after a turn while the user is idle: not work
                if stamp and stamp.date() > start and r.get('subtype') != 'away_summary':
                    s['stamps'].append(stamp)
        if s['cwd'] is None or ROOT not in s['cwd'].parents:
            continue  # outside ROOT, or at ROOT itself
        rel = s['cwd'].relative_to(ROOT)
        s['client'], s['cwd'] = rel.parts[0], str(rel)
        sessions.append(s)
    return sessions


def project(cwd, root=ROOT):
    """The client alone, or client/repo when the client is a directory of repos.

    A worktree counts as its main repository; a directory git does not know (or no longer
    exists) is the client alone."""
    client = root / cwd.relative_to(root).parts[0]
    if cwd == client or (client / '.git').exists():
        return client.name
    git = subprocess.run(['git', '-C', str(cwd), 'rev-parse', '--git-common-dir'],
                         capture_output=True, text=True)
    # relative to cwd in a main repo, absolute in a worktree; git resolves symlinks
    repo, base = (cwd / git.stdout.strip()).resolve().parent, client.resolve()
    if git.returncode or base not in repo.parents:
        return client.name
    return f'{client.name}/{repo.relative_to(base).parts[0]}'


def read_marker():
    return dt.date.fromisoformat(MARKER.read_text().strip())


def today():
    """A day is over GAP after midnight: an interval from 23:50 may still close at 00:10."""
    return (dt.datetime.now() - GAP).date()


def draft(since=None):
    start = dt.date.fromisoformat(since) if since else read_marker()
    end = today() - dt.timedelta(days=1)
    rows = {}
    for line in CSV.read_text(encoding='utf-8').splitlines()[1:]:
        date, name = line.split(',', 2)[:2]
        rows.setdefault((date, name.split('/')[0]), []).append(line)
    print(f'range: after {start} through {end}')
    for day, (wall, clients) in report(collect(start)).items():
        if day > end:
            continue
        print(f'{day}  wall clock {wall:.2f} h')
        for client, (total, shares) in sorted(clients.items()):
            print(f'  {client}  {total:.2f} h')
            for row in rows.get((str(day), client), []):
                print(f'    csv: {row}')
            for s, share in sorted(shares, key=lambda x: -x[1]):
                prompt = ' '.join(s['prompt'].split())[:80]
                print(f"    {share:.2f}  {project(ROOT / s['cwd'])}  {s['cwd']}  {s['title']}  | {prompt}")


# the harness renders systemMessage dim: \e[22m cancels the dim, then bold yellow
LOUD = '\x1b[22;1;33m'


def hook():
    """SessionStart: notice of days after the marker and before today with activity."""
    try:
        if (os.environ.get('CLAUDE_CODE_ENTRYPOINT', '').startswith('sdk-')
                or not Path(json.load(sys.stdin)['cwd']).is_relative_to(ROOT)):
            return
        days = [(d, sum(total for total, _ in clients.values()))
                for d, (_, clients) in report(collect(read_marker())).items() if d < today()]
        if days:
            listed = ', '.join(f'{d:%d.%m} ≈{h:.1f} h' for d, h in days)
            print(json.dumps({'systemMessage': f'{LOUD}⏱ unconfirmed: {listed} — /timelog\x1b[0m'}))
    except Exception as e:
        print(json.dumps({'systemMessage': f'{LOUD}⏱ timelog: script error ({e}) — /timelog\x1b[0m'}))


def test():
    def t(hm, day=1):
        return dt.datetime(2026, 10, day, *map(int, hm.split(':')))

    def sess(client, *stamps):
        return {'client': client, 'cwd': client, 'title': '', 'prompt': '', 'stamps': list(stamps)}

    oct1 = dt.date(2026, 10, 1)
    # Overlapping sessions of one client count once; of two clients, for each.
    a = sess('acme', t('10:00'), t('10:10'), t('10:20'))
    b = sess('acme', t('10:10'), t('10:20'), t('10:30'))
    c = sess('solo', t('10:00'), t('10:15'))
    wall, clients = report([a, b, c])[oct1]
    acme, shares = clients['acme']
    assert math.isclose(acme, 0.5), acme
    assert math.isclose(sum(share for _, share in shares), acme), shares
    assert math.isclose(clients['solo'][0], 0.25)
    assert math.isclose(wall, 0.5), wall
    # Gaps just under and over GAP.
    assert math.isclose(hours(intervals([t('10:00'), t('10:20')])), 1 / 3)
    assert intervals([t('10:00'), t('10:20:01')]) == []
    # An interval crossing midnight counts on the day it starts.
    r = report([sess('acme', t('23:50'), t('00:05', 2))])
    assert list(r) == [oct1] and math.isclose(r[oct1][0], 0.25), r
    # Duplicate stamps are no activity.
    assert report([sess('acme', t('10:00'), t('10:00'))]) == {}
    # collect(): the real transcript shape.
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp, '-home-projects-acme')
        proj.mkdir()

        def utc(x):
            return x.astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')

        def write(name, records, mtime=None):
            f = proj / name
            f.write_text('\n'.join(json.dumps(r) for r in records) + '\nnot json\n[1]\n',
                         encoding='utf-8')
            if mtime:
                os.utime(f, (mtime.timestamp(), mtime.timestamp()))

        web = str(ROOT / 'acme' / 'web')
        write('a.jsonl', [
            {'type': 'queue-operation', 'timestamp': utc(t('09:00'))},  # first record: no cwd
            {'type': 'user', 'cwd': web, 'timestamp': utc(t('23:55')),
             'message': {'content': '<command-name>/rev'}},
            {'type': 'user', 'cwd': web, 'timestamp': utc(t('10:00', 2)),
             'message': {'content': 'fix the map'}},
            {'type': 'ai-title', 'aiTitle': 'Map fix'},
            {'type': 'assistant', 'cwd': web, 'timestamp': utc(t('10:15', 2))},
            {'type': 'system', 'subtype': 'away_summary', 'cwd': web,
             'timestamp': utc(t('10:18', 2))},  # written while the user is idle
        ])
        pair = [utc(t('10:00', 2)), utc(t('10:10', 2))]
        write('root.jsonl', [{'type': 'user', 'cwd': str(ROOT), 'timestamp': x} for x in pair])
        write('old.jsonl', [{'type': 'user', 'cwd': web, 'timestamp': x} for x in pair],
              mtime=t('12:00'))
        sessions = collect(oct1, Path(tmp))
        assert len(sessions) == 1, sessions
        s = sessions[0]
        assert (s['client'], s['cwd'], s['title'], s['prompt']) == (
            'acme', 'acme/web', 'Map fix', 'fix the map'), s
        assert s['stamps'] == [t('10:00', 2), t('10:15', 2)], s['stamps']
    # project(): a repo client, a directory of repos, a worktree, a directory git does not know.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        def git(*args):
            subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t',
                            '-c', 'commit.gpgsign=false', *args],
                           cwd=root, check=True, capture_output=True)

        for d in ('solo/src', 'acme/notes'):
            (root / d).mkdir(parents=True)
        git('init', '-q', 'solo')
        git('init', '-q', 'acme/web')
        git('-C', 'acme/web', 'commit', '-q', '--allow-empty', '-m', 'x')
        git('-C', 'acme/web', 'worktree', 'add', '-q', '../web-worktrees/fix')
        (root / 'acme/web/src').mkdir()
        dirs = ['solo/src', 'acme', 'acme/notes', 'acme/web', 'acme/web/src',
                'acme/web-worktrees/fix', 'acme/gone']
        names = [project(root / d, root) for d in dirs]
        assert names == ['solo', 'acme', 'acme', 'acme/web', 'acme/web', 'acme/web', 'acme'], names
    print('ok')


if __name__ == '__main__':
    cmd, *args = sys.argv[1:]
    {'hook': hook, 'draft': draft, 'test': test}[cmd](*args)
