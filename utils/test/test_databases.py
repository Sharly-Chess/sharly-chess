import random
import string
import time

from database.sqlite.fide.fide_database import FideDatabase
from plugins.ffe.ffe_database import FfeDatabase

limit: int = 8
searches: int = 1000
test_fide: bool = True
test_ffe: bool = False

def random_search_token() -> str:
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(3))


if test_fide:
    t: float = time.time()
    print('Deleting the FIDE database...')
    FideDatabase().delete()
    print(f'Done in {int(time.time() - t)} seconds.')
    t: float = time.time()
    print('Creating the FIDE database...')
    if FideDatabase().create():
        print(f'Done in {int(time.time() - t)} seconds.')
        t: float = time.time()
        print(f'Performing {searches} searches on the FIDE database...')
        for _ in range(searches):
            token: str = random_search_token()
            with FideDatabase() as fide_database:
                print(f'Token [{token}]: {len(list(fide_database.search_player(random_search_token(), limit=limit)))}')
        print(f'Done in {int(time.time() - t)} seconds.')

if test_ffe:
    t: float = time.time()
    print('Deleting the FFE database...')
    FfeDatabase().delete()
    print(f'Done in {int(time.time() - t)} seconds.')
    t: float = time.time()
    print('Creating the FFE database...')
    if FfeDatabase().create():
        print(f'Done in {int(time.time() - t)} seconds.')
        t: float = time.time()
        print(f'Performing {searches} searches on the FFE database...')
        for _ in range(searches):
            token: str = random_search_token()
            with FfeDatabase() as ffe_database:
                print(f'Token [{token}]: {len(list(ffe_database.search_player(random_search_token(), limit=limit)))}')
        print(f'Done in {int(time.time() - t)} seconds.')
