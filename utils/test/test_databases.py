import random
import string
import time

from database.sqlite.fide.fide_database import FideDatabase
from plugins.ffe.ffe_database import FfeDatabase

limit: int = 8
searches: int = 100
test_fide: bool = True
test_ffe: bool = False
test_names: bool = True
test_ids: bool = True

def random_search_token() -> str:
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(3))


def random_search_id() -> str:
    return str(random.randrange(1000000))


if test_fide:
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
        if FideDatabase().create():
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
            print(f'Database size: {int(FideDatabase().file.lstat().st_size / 1024 / 1024)}Mb')
            if test_names:
                print(f'Performing {searches} name searches on the FIDE database (opening and closing each time)... ', end='')
                start: float = time.perf_counter()
                for _ in range(searches):
                    with FideDatabase() as fide_database:
                        #print(f'Token [{token}]: {len(list(fide_database.search_player(random_search_token(), limit=limit)))}')
                        fide_database.search_player(random_search_token(), limit=limit)
                duration: float = time.perf_counter() - start
                print(f'{duration:.2f} seconds.')
                start: float = time.perf_counter()
                with FideDatabase() as fide_database:
                    print(f'Performing {searches} name searches on the FIDE database (opening and closing once)... ', end='')
                    for _ in range(searches):
                        # print(f'Token [{token}]: {len(list(fide_database.search_player(random_search_token(), limit=limit)))}')
                        fide_database.search_player(random_search_token(), limit=limit)
                duration: float = time.perf_counter() - start
                print(f'{duration:.2f} seconds.')
            if test_ids:
                print(f'Performing {searches} integer searches on the FIDE database (opening and closing each time)... ', end='')
                start: float = time.perf_counter()
                for _ in range(searches):
                    with FideDatabase() as fide_database:
                        #print(f'Id [{id}]: {len(list(fide_database.search_player(str(id), limit=limit)))}')
                        fide_database.search_player(random_search_id(), limit=limit)
                duration: float = time.perf_counter() - start
                print(f'{duration:.2f} seconds.')
                print(f'Performing {searches} integer searches on the FIDE database (opening and closing once)... ', end='')
                start: float = time.perf_counter()
                with FideDatabase() as fide_database:
                    for _ in range(searches):
                        #print(f'Id [{id}]: {len(list(fide_database.search_player(str(id), limit=limit)))}')
                        fide_database.search_player(random_search_id(), limit=limit)
                duration: float = time.perf_counter() - start
                print(f'{duration:.2f} seconds.')

if test_ffe:
    print('Deleting the FFE database...')
    start: float = time.perf_counter()
    FfeDatabase().delete()
    duration: float = time.perf_counter() - start
    print(f'Done in {duration:.2f} seconds.')
    print('Creating the FFE database...')
    start: float = time.perf_counter()
    if FfeDatabase().create():
        duration: float = time.perf_counter() - start
        print(f'Done in {duration} seconds.')
        print(f'Performing {searches} searches on the FFE database...')
        start: float = time.perf_counter()
        for _ in range(searches):
            with FfeDatabase() as ffe_database:
                ffe_database.search_player(random_search_token(), limit=limit)
        duration: float = time.perf_counter() - start
        print(f'Done in {duration:.2f} seconds.')
