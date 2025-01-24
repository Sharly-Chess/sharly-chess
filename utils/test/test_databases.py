from database.sqlite.fide_database import FideDatabase

FideDatabase().delete()
if FideDatabase().create():
    print('Searching the database...')
    with FideDatabase() as fide_database:
        for player in fide_database.search_player('aub p'):
            print(f'player={player}')

#FfeDatabase().delete():
#if FfeDatabase().create():
#    print('Searching the database...')
#    with FfeDatabase() as ffe_database:
#        for player in ffe_database.search_player('cam 100013'):
#            print(f'player={player}')
#else:
#    print('No FFE database.')
