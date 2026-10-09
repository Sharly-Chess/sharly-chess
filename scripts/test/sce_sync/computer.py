"""One Sharly Chess installation taking part in a Sharly-Chess.com sync test.

Each installation is a data directory of its own (``--path``), so it has its
own configuration and computer identity, exactly as a second computer would.
The scenarios in ``run.py`` drive two of them; every command prints one JSON
document, prefixed by ``@@JSON@@``, on stdout.

    python scripts/test/sce_sync/computer.py --path DIR <command> [arguments]

``login`` opens the browser on the Sharly-Chess.com consent page and imports
the event chosen there. The other commands work on that event: ``state``,
``sync``, ``api`` (a v1 API request made with this installation's tokens),
and the local changes the scenarios need.
"""

import base64
import hashlib
import json
import secrets
import shutil
import sys
import threading
import webbrowser
from argparse import ArgumentParser, Namespace
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from utils.scripts import init_script

arguments = init_script()

import logging  # noqa: E402

import requests  # noqa: E402

from common.logger import set_logging_config  # noqa: E402
from data.event import Event  # noqa: E402
from data.loader import EventLoader  # noqa: E402
from data.player import TournamentPlayer  # noqa: E402
from database.sqlite.event.event_database import EventDatabase  # noqa: E402
from database.sqlite.event.event_store import (  # noqa: E402
    StoredPairing,
    StoredPlayer,
    StoredTournamentPlayer,
)
from plugins.ffe import PLUGIN_NAME as FFE_PLUGIN_NAME  # noqa: E402
from plugins.ffe.utils import FFEUtils  # noqa: E402
from plugins.sce import SCE_BASE_URL, sce_background_synchronizer  # noqa: E402
from plugins.sce.sce_admin_controller import SCEAdminController  # noqa: E402
from plugins.sce.sce_session import SCESession  # noqa: E402
from plugins.sce.utils import SCEUtils  # noqa: E402
from utils.enum import Result  # noqa: E402

CALLBACK_PATH = '/sce/oauth/callback/import-event'
COPY_SUFFIX = '-copy'

# Players hold their event weakly, so the loaded events are kept alive.
_loaded: list[Event] = []


def out(data: object) -> None:
    print('@@JSON@@' + json.dumps(data, default=str))


def only_event_uniq_id() -> str:
    uniq_ids = [
        uniq_id
        for uniq_id in EventLoader().event_uniq_ids
        if not uniq_id.endswith(COPY_SUFFIX)
    ]
    assert len(uniq_ids) == 1, f'Expected one event, found {uniq_ids}'
    return uniq_ids[0]


def load(uniq_id: str | None = None) -> Event:
    uniq_id = uniq_id or only_event_uniq_id()
    EventLoader.unload_event(uniq_id)
    event = EventLoader().load_event(uniq_id)
    _loaded.append(event)
    return event


def find_player(event: Event, last_name: str) -> TournamentPlayer:
    players = [p for p in event.players if p.last_name == last_name]
    assert len(players) == 1, f'{last_name}: {len(players)} players'
    return players[0].single_tournament_player


def cmd_login(args: Namespace) -> None:
    """Authorises this installation on Sharly-Chess.com and imports the event.

    The redirect lands on a loopback listener, which Sharly-Chess.com accepts
    on any port, so no Sharly Chess server needs to run.
    """
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b'=')
        .decode()
    )
    state = secrets.token_urlsafe(16)
    received: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            query = parse_qs(urlparse(self.path).query)
            received.update({key: values[0] for key, values in query.items()})
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Done, you can close this tab.')

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    redirect_uri = f'http://127.0.0.1:{server.server_port}{CALLBACK_PATH}'
    url = SCESession.build_oauth_url(redirect_uri, state, challenge)
    print(f'Authorise in the browser, or open: {url}', file=sys.stderr)
    webbrowser.open(url)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    thread.join(timeout=600)
    assert received.get('state') == state, 'No authorisation received'
    assert received.get('code'), f'Authorisation refused: {received}'
    tokens = SCESession.get_tokens_from_code(received['code'], verifier, redirect_uri)
    event = SCEAdminController._import_event(received['event_id'], tokens)
    plugin_data = SCEUtils.get_event_plugin_data(event)
    plugin_data.auto_upload = False
    plugin_data.auto_player_sync = False
    SCEUtils.update_event_plugin_data(event, plugin_data)
    if args.keep is not None:
        with EventDatabase(event.uniq_id, write=True) as database:
            for tournament in event.tournaments:
                if tournament.name not in args.keep:
                    database.delete_players_in_tournament(tournament.id)
                    database.delete_stored_tournament(tournament.id)
    out({'uniq_id': event.uniq_id, 'sce_event_id': received['event_id']})


def cmd_state(args: Namespace) -> None:
    event = load(args.event)
    ffe_enabled = FFE_PLUGIN_NAME in event.stored_event.enabled_plugins
    tournaments = []
    for tournament in event.tournaments:
        players = []
        for player in tournament.tournament_players:
            plugin_data = SCEUtils.get_player_plugin_data(player)
            players.append(
                {
                    'last_name': player.last_name,
                    'first_name': player.first_name,
                    'club': player.club.name,
                    'comment': player.comment,
                    'check_in': player.check_in,
                    'league': (
                        FFEUtils.get_player_plugin_data(player).league
                        if ffe_enabled
                        else None
                    ),
                    'sce_id': plugin_data.id,
                    'deleted_id': plugin_data.deleted_id,
                    'removal_pending': plugin_data.removal_pending,
                    'conflict': plugin_data.conflict_sync_data is not None,
                    'pairings': {
                        round_: pairing.result.name
                        for round_, pairing in player.pairings.items()
                        if pairing.result
                    },
                }
            )
        tournament_data = SCEUtils.get_tournament_plugin_data(tournament)
        tournaments.append(
            {
                'name': tournament.name,
                'rounds': tournament.rounds,
                'sce_id': tournament_data.id,
                'conflict': tournament_data.conflict_sync_data is not None,
                'players': players,
            }
        )
    event_data = SCEUtils.get_event_plugin_data(event)
    out(
        {
            'uniq_id': event.uniq_id,
            'sce_event_id': event_data.id,
            'tokens': event_data.tokens is not None,
            'token_device': event_data.tokens.device_id if event_data.tokens else None,
            'last_sync_status': event_data.last_sync_attempt_status,
            'deleted_player_ids': event_data.deleted_player_ids,
            'tournaments': tournaments,
        }
    )


def cmd_sync(args: Namespace) -> None:
    """Runs one synchronisation, as the background synchroniser does."""
    uniq_id = args.event or only_event_uniq_id()
    records: list[str] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    logger = logging.getLogger('sharly-chess')
    logger.addHandler(Collect(level=logging.DEBUG))
    logger.setLevel(logging.DEBUG)
    with (
        patch.object(sce_background_synchronizer, '_publish_upload_event'),
        patch('plugins.sce.sce_background_synchronizer.time.sleep'),
    ):
        sce_background_synchronizer.sync_event(uniq_id)
    event = load(uniq_id)
    out(
        {
            'status': SCEUtils.get_event_plugin_data(event).last_sync_attempt_status,
            'log': [r for r in records if 'Sharly-Chess.com sync' in r or 'SCE' in r],
        }
    )


def cmd_edit(args: Namespace) -> None:
    """Changes fields of a player locally: ``club=X``, ``league=EXP``…"""
    event = load()
    player = find_player(event, args.name)
    stored = player.stored_player
    for assignment in args.set:
        field, value = assignment.split('=', 1)
        parsed: object = None if value == 'None' else value
        if field == 'check_in':
            parsed = value == 'true'
        if field == 'league':
            ffe_data = FFEUtils.get_player_plugin_data(player)
            ffe_data.league = parsed  # type: ignore[assignment]
            stored.plugin_data[FFE_PLUGIN_NAME] = ffe_data.to_stored_value()
        else:
            setattr(stored, field, parsed)
    with EventDatabase(event.uniq_id, write=True) as database:
        database.update_stored_player(stored)
    out({'ok': True})


def cmd_add(args: Namespace) -> None:
    event = load()
    tournament = event.tournaments_by_name[args.tournament]
    with EventDatabase(event.uniq_id, write=True) as database:
        player_id = database.add_stored_player(
            StoredPlayer(
                id=None,
                last_name=args.name,
                first_name='Live',
                year_of_birth=1990,
                federation='FRA',
            )
        )
        database.add_stored_tournament_player(
            StoredTournamentPlayer(player_id=player_id, tournament_id=tournament.id)
        )
    out({'player_id': player_id})


def cmd_delete(args: Namespace) -> None:
    event = load()
    player = find_player(event, args.name)
    event.delete_player(event.players_by_id[player.id])
    out({'ok': True})


def cmd_pair(args: Namespace) -> None:
    """Gives the player the pairing-allocated bye of a round, which makes
    them a player who has played."""
    event = load()
    player = find_player(event, args.name)
    with EventDatabase(event.uniq_id, write=True) as database:
        database.add_stored_pairing(
            StoredPairing(
                tournament_id=player.tournament.id,
                player_id=player.id,
                round_=args.round,
                result=Result.PAIRING_ALLOCATED_BYE.value,
                board_id=None,
            )
        )
    out({'ok': True})


def cmd_bye(args: Namespace) -> None:
    event = load()
    player = find_player(event, args.name)
    player.tournament.set_player_byes(player, {args.round: Result[args.result]})
    out({'ok': True})


def cmd_withdraw(args: Namespace) -> None:
    SCESession.withdraw_removed_player(find_player(load(), args.name))
    out({'ok': True})


def cmd_keep(args: Namespace) -> None:
    SCESession.register_removed_player_again(find_player(load(), args.name))
    out({'ok': True})


def cmd_import_tournament(args: Namespace) -> None:
    event = load()
    session = SCESession(event)
    data = session._get_event_data()
    ids = [t['id'] for t in data['tournaments'] if t['name'] == args.tournament]
    assert len(ids) == 1, f'{args.tournament}: {len(ids)} tournaments'
    session.import_tournaments(ids)
    out({'sce_id': ids[0]})


def cmd_set_rounds(args: Namespace) -> None:
    event = load()
    stored = event.tournaments_by_name[args.tournament].stored_tournament
    stored.rounds = args.rounds
    with EventDatabase(event.uniq_id, write=True) as database:
        database.update_stored_tournament(stored)
    out({'ok': True})


def cmd_create_local_tournament(args: Namespace) -> None:
    from tests.test_config import TestUtils

    event = load()
    TestUtils.create_tournament(event.uniq_id, args.tournament)
    out({'ok': True})


def cmd_upload_tournament(args: Namespace) -> None:
    event = load()
    tournament = event.tournaments_by_name[args.tournament]
    out({'duplicates': SCESession(event).create_sce_tournament(tournament)})


def cmd_copy_event_to(args: Namespace) -> None:
    """Copies the event file into another installation, as a user copying
    it to another computer would."""
    event = load()
    source = Path(EventDatabase.event_database_path(event.uniq_id)).resolve()
    relative = source.parent.relative_to(Path.cwd().resolve())
    uniq_id = f'{event.uniq_id}{COPY_SUFFIX}'
    target = Path(args.dest) / relative / f'{uniq_id}{source.suffix}'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, target)
    out({'copied_to': str(target), 'uniq_id': uniq_id})


def cmd_expire_token(args: Namespace) -> None:
    """Makes the next request refresh the access token."""
    event = load(args.event)
    plugin_data = SCEUtils.get_event_plugin_data(event)
    assert plugin_data.tokens is not None
    plugin_data.tokens.expires_at -= timedelta(days=1)
    SCEUtils.update_event_plugin_data(event, plugin_data)
    out({'ok': True})


def cmd_api(args: Namespace) -> None:
    """A v1 API request on the event, made with this installation's tokens."""
    event = load(args.event)
    session = SCESession(event)
    url = f'{SCE_BASE_URL}/api/v1/events/{session.sce_event_id}{args.path}'
    body = json.loads(args.json) if args.json else None

    def request() -> requests.Response:
        return requests.request(
            args.method, url, headers=session.api_headers, json=body, timeout=15
        )

    response = session._run_with_token_validation(request, skip_validation=True)
    try:
        data = response.json()
    except ValueError:
        data = response.text
    out({'status': response.status_code, 'body': data})


def main() -> None:
    set_logging_config()
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('login')
    command.add_argument(
        '--keep', nargs='*', help='Tournaments to keep locally (all by default).'
    )
    for name in ('state', 'sync', 'expire-token'):
        commands.add_parser(name).add_argument('--event')
    command = commands.add_parser('edit')
    command.add_argument('name')
    command.add_argument('set', nargs='+')
    command = commands.add_parser('add')
    command.add_argument('tournament')
    command.add_argument('name')
    for name in ('delete', 'withdraw', 'keep'):
        commands.add_parser(name).add_argument('name')
    command = commands.add_parser('pair')
    command.add_argument('name')
    command.add_argument('round', type=int)
    command = commands.add_parser('bye')
    command.add_argument('name')
    command.add_argument('round', type=int)
    command.add_argument('result')
    for name in (
        'import-tournament',
        'create-local-tournament',
        'upload-tournament',
    ):
        commands.add_parser(name).add_argument('tournament')
    command = commands.add_parser('set-rounds')
    command.add_argument('tournament')
    command.add_argument('rounds', type=int)
    commands.add_parser('copy-event-to').add_argument('dest')
    command = commands.add_parser('api')
    command.add_argument('method')
    command.add_argument('path')
    command.add_argument('json', nargs='?')
    command.add_argument('--event')
    args = parser.parse_args(arguments)
    globals()['cmd_' + args.command.replace('-', '_')](args)


if __name__ == '__main__':
    main()
