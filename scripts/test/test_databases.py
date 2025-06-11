from asyncio import run
import random
import string
import time

# Import this first to avoid circular imports
import plugins.manager  # noqa
from common.exception import SharlyChessException
from common.logger import (
    print_interactive_info,
    print_interactive_error,
    print_interactive_success,
)
from data.player import Player
from database.sqlite.fide.fide_database import FideDatabase
from plugins.ffe.ffe_database import FfeDatabase
from plugins.ffe.ffe_sql_server import FFESqlServer

limit: int = 8
searches: int = 100
test_names: bool = True
test_ids: bool = True


def random_search_token() -> str:
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(3))


def random_search_id() -> str:
    return str(random.randrange(1000000))


def test_fide_local_database():
    name_sql_commands: dict[str, str] = {
        'first_name': 'CREATE INDEX `player_first_name` ON `player` (`first_name` COLLATE NOCASE)',
        'last_name': 'CREATE INDEX `player_last_name` ON `player` (`last_name` COLLATE NOCASE)',
    }
    id_sql_commands: dict[str, str] = {
        'fide_id': 'CREATE INDEX `player_fide_id` ON `player` (`fide_id`)',
    }
    sql_commands_list: list[dict[str, str]] = [
        {},
        name_sql_commands,
        id_sql_commands,
        name_sql_commands | id_sql_commands,
    ]
    for sql_commands in sql_commands_list:
        FideDatabase().delete()
        start: float = time.perf_counter()
        print('Creating the FIDE database... ')
        duration: float = time.perf_counter() - start
        if FideDatabase().update():
            print(f'Done in {duration:.2f} seconds.')
            if sql_commands:
                print(f'Adding indices ({", ".join(sql_commands.keys())})... ', end='')
                start: float = time.perf_counter()
                for sql_command in sql_commands.values():
                    with FideDatabase(write=True) as fide_database:
                        fide_database.execute(sql_command)
                        fide_database.commit()
                duration: float = time.perf_counter() - start
                print(f'{duration:.2f} seconds.')
            print(
                f'Database size: {int(FideDatabase().file.lstat().st_size / 1024 / 1024)}Mb'
            )
            if test_names:
                print(
                    f'Performing {searches} name searches on the FIDE database (opening and closing each time)... ',
                    end='',
                )
                start: float = time.perf_counter()
                for _ in range(searches):
                    with FideDatabase() as fide_database:
                        # print(f'Token [{token}]: {len(list(fide_database.search_player(random_search_token(), limit=limit)))}')
                        fide_database.search_player(random_search_token(), limit=limit)
                duration: float = time.perf_counter() - start
                print(f'{duration:.2f} seconds.')
                start: float = time.perf_counter()
                with FideDatabase() as fide_database:
                    print(
                        f'Performing {searches} name searches on the FIDE database (opening and closing once)... ',
                        end='',
                    )
                    for _ in range(searches):
                        # print(f'Token [{token}]: {len(list(fide_database.search_player(random_search_token(), limit=limit)))}')
                        fide_database.search_player(random_search_token(), limit=limit)
                duration: float = time.perf_counter() - start
                print(f'{duration:.2f} seconds.')
            if test_ids:
                print(
                    f'Performing {searches} integer searches on the FIDE database (opening and closing each time)... ',
                    end='',
                )
                start: float = time.perf_counter()
                for _ in range(searches):
                    with FideDatabase() as fide_database:
                        # print(f'Id [{id}]: {len(list(fide_database.search_player(str(id), limit=limit)))}')
                        fide_database.search_player(random_search_id(), limit=limit)
                duration: float = time.perf_counter() - start
                print(f'{duration:.2f} seconds.')
                print(
                    f'Performing {searches} integer searches on the FIDE database (opening and closing once)... ',
                    end='',
                )
                start: float = time.perf_counter()
                with FideDatabase() as fide_database:
                    for _ in range(searches):
                        # print(f'Id [{id}]: {len(list(fide_database.search_player(str(id), limit=limit)))}')
                        fide_database.search_player(random_search_id(), limit=limit)
                duration: float = time.perf_counter() - start
                print(f'{duration:.2f} seconds.')


def test_ffe_local_database():
    print('Deleting the FFE database...')
    start: float = time.perf_counter()
    FfeDatabase().delete()
    duration: float = time.perf_counter() - start
    print(f'Done in {duration:.2f} seconds.')
    print('Creating the FFE database...')
    start: float = time.perf_counter()
    if FfeDatabase().update():
        duration: float = time.perf_counter() - start
        print(f'Done in {duration} seconds.')
        print(f'Performing {searches} searches on the FFE database...')
        start: float = time.perf_counter()
        for _ in range(searches):
            with FfeDatabase() as ffe_database:
                ffe_database.search_player(random_search_token(), limit=limit)
        duration: float = time.perf_counter() - start
        print(f'Done in {duration:.2f} seconds.')


async def search_ffe_sql_server_token(token: str, limit: int = 0) -> list[Player]:
    result: list[Player] = []
    print_interactive_info(
        '--------------------------------------------------------------------------------------------------------------------------------------------------------'
    )
    print_interactive_info(f'Searching token [{token}] in the FFE SQL server...')
    start: float = time.perf_counter()
    try:
        async with FFESqlServer() as ffe_sql_server:
            async for player in await ffe_sql_server.search_player(
                str(token), limit=limit
            ):
                if player.fide_id:
                    print_interactive_info(f'{player=}')
                    result.append(player)
    except SharlyChessException as exception:
        print_interactive_error(f'{exception=}')
    duration: float = time.perf_counter() - start
    print(f'Done in {duration:.2f} seconds.')
    return result


async def search_ffe_sql_server_fide_id(player_fide_id: int) -> list[Player]:
    result: list[Player] = []
    print_interactive_info(
        f'Searching FIDE ID [{player_fide_id}] in the FFE SQL server...'
    )
    start: float = time.perf_counter()
    try:
        async with FFESqlServer() as ffe_sql_server:
            async for player in await ffe_sql_server.search_player(
                str(player_fide_id), limit=2
            ):
                result.append(player)
                print_interactive_success(f'{player_fide_id=}, {player=}')
    except SharlyChessException as exception:
        print_interactive_error(f'{exception=}')
    duration: float = time.perf_counter() - start
    print(f'Done in {duration:.2f} seconds.')
    return result


async def test_ffe_sql_server():
    players = await search_ffe_sql_server_token('all', limit=30)
    print_interactive_info(
        '--------------------------------------------------------------------------------------------------------------------------------------------------------'
    )
    for player in players:
        await search_ffe_sql_server_fide_id(player.fide_id)


if __name__ == '__main__':
    run(test_ffe_sql_server())
