"""Sharly-Chess.com sync scenarios between two installations, run by hand.

Two installations of the working copy, A and B, are linked to one test event
on Sharly-Chess.com, each with its own data directory and so its own computer
identity. A holds tournament T1 only, as an arbiter would; B holds T1, T2 and
T3 and also plays the organiser, making changes on Sharly-Chess.com through
the v1 API with its own tokens. Each scenario creates the registrations it
needs, named ``LIVE<tag>…``, checks both installations and Sharly-Chess.com,
and deletes them again.

Setting up, once (the tokens then last as long as they are used at least
every 30 days):

    python scripts/test/sce_sync/run.py --setup

This opens the browser twice on the Sharly-Chess.com consent page: choose the
test event each time. Tournaments T1, T2 and T3 are created on the event when
it lacks them. Then:

    python scripts/test/sce_sync/run.py                  # every scenario
    python scripts/test/sce_sync/run.py check_in_kept    # some of them
    python scripts/test/sce_sync/run.py --list
    python scripts/test/sce_sync/run.py --cleanup        # leftover registrations

``--with-upload`` adds the upload of a local tournament, which leaves a
tournament on the test event: the API cannot delete it. ``SCE_BASE_URL``
points both installations at another Sharly-Chess.com server. The data
directories live in ``tmp/sce-sync`` unless ``--work-dir`` says otherwise;
delete it to start again from ``--setup``.
"""

import json
import os
import secrets
import subprocess
import sys
import traceback
from argparse import ArgumentParser
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
TOURNAMENTS = ('T1', 'T2', 'T3')
DEFAULT_ROUNDS = 7

dirs: dict[str, Path] = {}
failures: list[str] = []
passes = 0
sync_log: list[str] = []


def run(computer: str, *args: str, interactive: bool = False) -> dict[str, Any]:
    env = {key: value for key, value in os.environ.items() if key != 'TEST_ENV'}
    env['PYTHONPATH'] = os.pathsep.join([str(REPO / 'src'), str(REPO)])
    result = subprocess.run(
        [
            sys.executable,
            str(HERE / 'computer.py'),
            '--path',
            str(dirs[computer]),
            *args,
        ],
        stdout=subprocess.PIPE,
        stderr=None if interactive else subprocess.PIPE,
        text=True,
        env=env,
        check=False,
    )
    for line in result.stdout.splitlines():
        if line.startswith('@@JSON@@'):
            return json.loads(line.removeprefix('@@JSON@@'))
    raise RuntimeError(
        f'{computer} {args} failed:\n{result.stdout[-2000:]}\n'
        f'{(result.stderr or "")[-4000:]}'
    )


def check(label: str, condition: object, detail: object = '') -> None:
    global passes
    if condition:
        passes += 1
        print(f'  PASS {label}')
    else:
        failures.append(label)
        print(f'  FAIL {label} {detail}')


def state(computer: str, event: str | None = None) -> dict[str, Any]:
    return run(computer, 'state', *(['--event', event] if event else []))


def player(computer: str, name: str, event: str | None = None) -> dict | None:
    for tournament in state(computer, event)['tournaments']:
        for found in tournament['players']:
            if found['last_name'] == name:
                return found | {'tournament': tournament['name']}
    return None


def sync(computer: str, event: str | None = None) -> str:
    result = run(computer, 'sync', *(['--event', event] if event else []))
    sync_log.extend(f'{computer}: {line}' for line in result['log'])
    return result['status']


def api(method: str, path: str, body: dict | None = None) -> dict[str, Any]:
    args = [method, path]
    if body is not None:
        args.append(json.dumps(body))
    return run('B', 'api', *args)


def remote_tournaments() -> list[dict[str, Any]]:
    return api('GET', '?with_active_registrations=true')['body']['data']['tournaments']


def remote() -> dict[str, dict[str, Any]]:
    """Every active registration on Sharly-Chess.com, by id."""
    return {
        registration['id']: registration | {'tournament_id': tournament['id']}
        for tournament in remote_tournaments()
        for registration in tournament['registrations']
    }


def remote_by_name(name: str) -> dict[str, Any] | None:
    matches = [r for r in remote().values() if r['last_name'] == name]
    return matches[0] if matches else None


def tournament_rounds(sce_id: str) -> int:
    for tournament in remote_tournaments():
        if tournament['id'] == sce_id:
            return int(tournament['number_of_rounds'])
    return DEFAULT_ROUNDS


def delete_live_registrations(prefix: str = 'LIVE') -> None:
    for registration_id, registration in remote().items():
        if registration['last_name'].startswith(prefix):
            api(
                'DELETE',
                f'/tournaments/{registration["tournament_id"]}'
                f'/registrations/{registration_id}',
            )
    sync('A')
    sync('B')


class Scenario:
    def __init__(self) -> None:
        self.tag = secrets.token_hex(3).upper()
        self.t = {t['name']: t['sce_id'] for t in state('B')['tournaments']}

    def name(self, base: str) -> str:
        return f'LIVE{self.tag}{base}'

    def registration_url(self, tournament: str, registration_id: str) -> str:
        return f'/tournaments/{self.t[tournament]}/registrations/{registration_id}'

    def register(self, tournament: str, name: str) -> str:
        response = api(
            'POST',
            f'/tournaments/{self.t[tournament]}/registrations',
            {
                'last_name': name,
                'first_name': 'Live',
                'year_of_birth': 1990,
                'federation': 'FRA',
            },
        )
        assert response['status'] in (200, 201), response
        return str(response['body']['data']['id'])

    def cleanup(self) -> None:
        delete_live_registrations(f'LIVE{self.tag}')


# ---------------------------------------------------------------------------
# Scenarios


def s_partial_edits(s: Scenario) -> None:
    """Different fields changed on two computers both survive."""
    p = s.name('EDIT')
    s.register('T1', p)
    sync('A')
    sync('B')
    run('A', 'edit', p, 'club=Club A')
    run('B', 'edit', p, 'comment=Comment B')
    sync('A')
    sync('B')
    sync('A')
    r = remote_by_name(p)
    check('club from A on SC.com', r and r['club'] == 'Club A', r)
    check('comment from B on SC.com', r and r['comment'] == 'Comment B', r)
    a, b = player('A', p), player('B', p)
    check('A has both', a and (a['club'], a['comment']) == ('Club A', 'Comment B'), a)
    check('B has both', b and (b['club'], b['comment']) == ('Club A', 'Comment B'), b)


def s_check_in_kept(s: Scenario) -> None:
    """A check-in made on SC.com survives another field being pushed."""
    p = s.name('CHECKIN')
    registration_id = s.register('T1', p)
    sync('A')
    api('POST', s.registration_url('T1', registration_id) + '/check-in')
    run('A', 'edit', p, 'comment=After check-in')
    sync('A')
    r = remote_by_name(p)
    check('still checked in on SC.com', r and r['checked_in'] is True, r)
    check('comment pushed', r and r['comment'] == 'After check-in', r)
    a = player('A', p)
    check('A sees the check-in', a and a['check_in'] is True, a)


def s_same_field_conflict(s: Scenario) -> None:
    """The same field changed on two computers is a conflict, not an overwrite."""
    p = s.name('CONFLICT')
    s.register('T1', p)
    sync('A')
    sync('B')
    run('A', 'edit', p, 'club=Club A')
    run('B', 'edit', p, 'club=Club B')
    sync('A')
    status = sync('B')
    b = player('B', p)
    check('B reports player conflicts', 'CONFLICT' in (status or ''), status)
    check('B player has a conflict', b and b['conflict'], b)
    r = remote_by_name(p)
    check('SC.com keeps A value', r and r['club'] == 'Club A', r)


def removed_after_playing(s: Scenario, base: str) -> tuple[str, int]:
    p = s.name(base)
    registration_id = s.register('T1', p)
    sync('A')
    run('A', 'pair', p, '1')
    api('DELETE', s.registration_url('T1', registration_id))
    sync('A')
    return p, tournament_rounds(s.t['T1'])


def s_paired_removed_withdraw(s: Scenario) -> None:
    """A player removed on SC.com after playing waits for the arbiter, who
    withdraws them."""
    p, rounds = removed_after_playing(s, 'WITHDRAW')
    a = player('A', p)
    check('paired player kept', a is not None, a)
    check('pending decision', a and a['removal_pending'], a)
    check('no byes added', a and set(a['pairings']) == {'1'}, a)
    run('A', 'bye', p, '4', 'HALF_POINT_BYE')
    run('A', 'withdraw', p)
    a = player('A', p)
    expected = {str(r): 'ZERO_POINT_BYE' for r in range(2, rounds + 1)}
    expected |= {'1': 'PAIRING_ALLOCATED_BYE', '4': 'HALF_POINT_BYE'}
    check('byes after withdraw', a and a['pairings'] == expected, a)
    check('decision closed', a and not a['removal_pending'], a)
    sync('A')
    check('withdrawn player not registered again', remote_by_name(p) is None)


def s_paired_removed_keep(s: Scenario) -> None:
    """A player removed on SC.com after playing is kept by the arbiter."""
    p, _ = removed_after_playing(s, 'KEEP')
    run('A', 'keep', p)
    sync('A')
    a = player('A', p)
    r = remote_by_name(p)
    check('registered again on SC.com', r and r['tournament_id'] == s.t['T1'], r)
    check('linked to the new registration', a and r and a['sce_id'] == r['id'], a)
    check('pairings untouched', a and set(a['pairings']) == {'1'}, a)


def s_move_unpaired_away(s: Scenario) -> None:
    """A move to a tournament A does not hold removes the player from A only."""
    p = s.name('MOVE')
    registration_id = s.register('T1', p)
    sync('A')
    api(
        'PATCH', s.registration_url('T1', registration_id), {'tournament_id': s.t['T3']}
    )
    sync('A')
    check('removed from A', player('A', p) is None)
    r = remote_by_name(p)
    check('still on SC.com in T3', r and r['tournament_id'] == s.t['T3'], r)
    check('nothing queued on A', not state('A')['deleted_player_ids'])
    sync('B')
    b = player('B', p)
    check('B has it in T3', b and b['tournament'] == 'T3', b)


def s_move_paired_away(s: Scenario) -> None:
    """A player who has played is moved back to their tournament."""
    p = s.name('MOVEPAIRED')
    registration_id = s.register('T1', p)
    sync('A')
    run('A', 'pair', p, '1')
    api(
        'PATCH', s.registration_url('T1', registration_id), {'tournament_id': s.t['T3']}
    )
    sync('A')
    a = player('A', p)
    check(
        'kept on A, linked',
        a and a['sce_id'] == registration_id and a['tournament'] == 'T1',
        a,
    )
    r = remote_by_name(p)
    check('forced back to T1 on SC.com', r and r['tournament_id'] == s.t['T1'], r)


def s_sync_deletion_not_queued(s: Scenario) -> None:
    """A player removed by the sync is not deleted on SC.com in turn."""
    p = s.name('GONE')
    registration_id = s.register('T1', p)
    sync('A')
    api('DELETE', s.registration_url('T1', registration_id))
    sync('A')
    check('removed from A', player('A', p) is None)
    check(
        'nothing queued on A', registration_id not in state('A')['deleted_player_ids']
    )


def s_local_deletion_sent(s: Scenario) -> None:
    """A player deleted locally is deleted on SC.com."""
    p = s.name('LOCALDEL')
    s.register('T2', p)
    sync('B')
    run('B', 'delete', p)
    sync('B')
    check('deleted on SC.com', remote_by_name(p) is None)
    check('queue emptied', not state('B')['deleted_player_ids'])


def s_conflicts_do_not_block(s: Scenario) -> None:
    """A tournament conflict does not stop the players from syncing."""
    rounds = tournament_rounds(s.t['T2'])
    try:
        api('PATCH', f'/tournaments/{s.t["T2"]}', {'number_of_rounds': rounds + 1})
        run('B', 'set-rounds', 'T2', str(rounds + 2))
        q = s.name('AFTERCONFLICT')
        s.register('T2', q)
        status = sync('B')
        check('tournament conflict reported', status == 'TOURNAMENT_CONFLICTS', status)
        check('player still imported', player('B', q) is not None)
    finally:
        api('PATCH', f'/tournaments/{s.t["T2"]}', {'number_of_rounds': rounds})
        run('B', 'set-rounds', 'T2', str(rounds))
        status = sync('B')
        check('conflict gone once equal', status != 'TOURNAMENT_CONFLICTS', status)


def s_copied_event(s: Scenario) -> None:
    """A copied event file asks to be connected, and the original keeps working."""
    copy = run('A', 'copy-event-to', str(dirs['B']))['uniq_id']
    try:
        status = sync('B', copy)
        copied = state('B', copy)
        check('copy asks for re-auth', status == 'AUTH_FAILURE', status)
        check('copy dropped its tokens', not copied['tokens'], copied['tokens'])
        run('A', 'expire-token')
        status = sync('A')
        check('A still refreshes and syncs', status == 'SUCCESS', status)
        check('A still has tokens', state('A')['tokens'])
    finally:
        for file in dirs['B'].rglob(f'{copy}.*'):
            file.unlink()


def s_ffe_leagues(s: Scenario) -> None:
    """A league SC.com does not know is neither sent nor cleared locally."""
    p = s.name('LEAGUE')
    registration_id = s.register('T1', p)
    sync('A')
    run('A', 'edit', p, 'league=EXP')
    sync('A')
    sync('A')
    r = remote_by_name(p)
    check('EXP not sent', r and r['ffe_league'] is None, r)
    check('A keeps EXP', (player('A', p) or {}).get('league') == 'EXP')
    url = s.registration_url('T1', registration_id)
    api('PATCH', url, {'club': 'Pulled'})
    sync('A')
    a = player('A', p) or {}
    check(
        'pulled change applied, EXP kept',
        (a.get('club'), a.get('league')) == ('Pulled', 'EXP'),
        a,
    )
    api('PATCH', url, {'ffe_league': 'BRE'})
    sync('A')
    check('known league replaces EXP', (player('A', p) or {}).get('league') == 'BRE')
    run('A', 'edit', p, 'league=EXP')
    sync('A')
    r = remote_by_name(p)
    check('leaving the leagues clears it on SC.com', r and r['ffe_league'] is None, r)
    check('A keeps EXP', (player('A', p) or {}).get('league') == 'EXP')


def s_upload_local_tournament(s: Scenario) -> None:
    """Uploading a local tournament registers its players at once."""
    name = s.name('UP')
    run('B', 'create-local-tournament', name)
    run('B', 'add', name, s.name('UP1'))
    run('B', 'add', name, s.name('UP2'))
    run('B', 'upload-tournament', name)
    found = {r['last_name'] for r in remote().values()}
    check('players registered at upload', {s.name('UP1'), s.name('UP2')} <= found)


SCENARIOS: dict[str, Callable[[Scenario], None]] = {
    'partial_edits': s_partial_edits,
    'check_in_kept': s_check_in_kept,
    'same_field_conflict': s_same_field_conflict,
    'paired_removed_withdraw': s_paired_removed_withdraw,
    'paired_removed_keep': s_paired_removed_keep,
    'move_unpaired_away': s_move_unpaired_away,
    'move_paired_away': s_move_paired_away,
    'sync_deletion_not_queued': s_sync_deletion_not_queued,
    'local_deletion_sent': s_local_deletion_sent,
    'conflicts_do_not_block': s_conflicts_do_not_block,
    'copied_event': s_copied_event,
    'ffe_leagues': s_ffe_leagues,
}
ALL_SCENARIOS: dict[str, Callable[[Scenario], None]] = {
    **SCENARIOS,
    'upload_local_tournament': s_upload_local_tournament,
}


# ---------------------------------------------------------------------------


def setup() -> None:
    for directory in dirs.values():
        if any(directory.rglob('*.sce')):
            sys.exit(f'{directory} already holds an event: delete it to set up again.')
    print('Computer A: authorise the test event in the browser.')
    run('A', 'login', '--keep', 'T1', interactive=True)
    existing = {t['name'] for t in remote_tournaments_of('A')}
    for name in TOURNAMENTS:
        if name not in existing:
            response = run(
                'A',
                'api',
                'POST',
                '/tournaments',
                json.dumps(
                    {
                        'name': name,
                        'type': 'rapid',
                        'number_of_rounds': DEFAULT_ROUNDS,
                        'start_date': date.today().isoformat(),
                        'criteria': {},
                    }
                ),
            )
            assert response['status'] == 201, response
            print(f'Created {name} on Sharly-Chess.com.')
    if not any(t['name'] == 'T1' for t in state('A')['tournaments']):
        run('A', 'import-tournament', 'T1')
    print('Computer B: authorise the same test event in the browser.')
    run('B', 'login', interactive=True)
    for computer in dirs:
        names = [t['name'] for t in state(computer)['tournaments']]
        print(f'{computer} holds {names}')


def remote_tournaments_of(computer: str) -> list[dict[str, Any]]:
    return run(computer, 'api', 'GET', '')['body']['data']['tournaments']


def main() -> None:
    parser = ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument(
        'scenarios', nargs='*', help='Scenarios to run (all by default).'
    )
    parser.add_argument(
        '--setup', action='store_true', help='Link A and B to the test event.'
    )
    parser.add_argument(
        '--cleanup', action='store_true', help='Delete leftover LIVE registrations.'
    )
    parser.add_argument('--list', action='store_true', help='List the scenarios.')
    parser.add_argument(
        '--with-upload', action='store_true', help='Also upload a local tournament.'
    )
    parser.add_argument('--work-dir', type=Path, default=REPO / 'tmp' / 'sce-sync')
    args = parser.parse_args()
    dirs.update({'A': args.work_dir / 'A', 'B': args.work_dir / 'B'})
    scenarios = list(ALL_SCENARIOS if args.with_upload else SCENARIOS)
    if args.list:
        for name, function in ALL_SCENARIOS.items():
            print(f'{name}: {(function.__doc__ or "").strip()}')
        return
    if args.setup:
        setup()
        return
    if args.cleanup:
        delete_live_registrations()
        return
    unknown = set(args.scenarios) - set(ALL_SCENARIOS)
    if unknown:
        sys.exit(f'Unknown scenarios: {", ".join(sorted(unknown))}')
    for name in args.scenarios or scenarios:
        print(f'== {name}')
        sync_log.clear()
        failed_before = len(failures)
        scenario = Scenario()
        try:
            ALL_SCENARIOS[name](scenario)
        except Exception:
            failures.append(f'{name}: exception')
            traceback.print_exc()
        finally:
            if len(failures) > failed_before:
                print('  sync log:')
                for line in sync_log:
                    print(f'    {line}')
            try:
                scenario.cleanup()
            except Exception:
                traceback.print_exc()
    print(f'\n{passes} passed, {len(failures)} failed')
    for failure in failures:
        print(f'  - {failure}')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
