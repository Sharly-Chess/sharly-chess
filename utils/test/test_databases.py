from plugins.ffe.ffe_database import FfeDatabase
from database.sqlite.fide_database import FideDatabase

limit: int = 8

#FideDatabase().delete()
#if FideDatabase().create():
#    print('Searching the database...')
#    with FideDatabase() as fide_database:
#        for player in fide_database.search_player('aub p', limit=limit):
#            print(f'player={player}')

# FfeDatabase().delete():
# if FfeDatabase().create():
#    print('Searching the database...')
with FfeDatabase() as ffe_database:
    for player in ffe_database.search_player('aub p', limit=limit):
        print(f'player={player}')
# else:
#    print('No FFE database.')
