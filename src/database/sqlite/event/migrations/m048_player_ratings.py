import json
from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute('SELECT `id`, `ratings` FROM `player`')
        for row in self.database.fetchall():
            player_id = row['id']
            dict_ratings = json.loads(row['ratings'])
            new_ratings = {}
            for tournament_rating_type, ratings in dict_ratings.items():
                match ratings['type']:
                    case 1:
                        new_ratings[tournament_rating_type] = {
                            'estimated': ratings['value']
                        }
                    case 2:
                        new_ratings[tournament_rating_type] = {
                            'national': ratings['value']
                        }
                    case 3:
                        new_ratings[tournament_rating_type] = {'fide': ratings['value']}
            self.database.execute(
                'UPDATE `player` SET `ratings` = ? WHERE `id` = ?',
                (json.dumps(new_ratings), player_id),
            )

    def backward(self):
        self.database.execute('SELECT `id`, `ratings` FROM `player`')
        for row in self.database.fetchall():
            player_id = row['id']
            dict_ratings = json.loads(row['ratings'])
            old_ratings = {}
            for tournament_rating_type, ratings in dict_ratings.items():
                if 'fide' in ratings:
                    old_ratings[tournament_rating_type] = {
                        'value': ratings['fide'],
                        'type': 3,
                    }
                elif 'national' in ratings:
                    old_ratings[tournament_rating_type] = {
                        'value': ratings['national'],
                        'type': 2,
                    }
                elif 'estimated' in ratings:
                    old_ratings[tournament_rating_type] = {
                        'value': ratings['estimated'],
                        'type': 1,
                    }
            self.database.execute(
                'UPDATE `player` SET `ratings` = ? WHERE `id` = ?',
                (json.dumps(old_ratings), player_id),
            )
