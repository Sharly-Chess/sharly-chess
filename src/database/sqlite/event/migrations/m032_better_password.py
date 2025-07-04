from database.sqlite.migration import BaseMigration
from argon2 import PasswordHasher


class Migration(BaseMigration):
    # NOTE(Amaras): because we hash the passwords, it is fully impossible
    # to reverse this migration non-destructively
    def forward(self):
        ph = PasswordHasher()
        self.database.execute('SELECT `id`, `password` FROM `account`')
        accounts = self.database.fetchall()
        password_hashes = [
            {'id': row['id'], 'hash': ph.hash(row['password'])} for row in accounts
        ]

        self.database.execute('ALTER TABLE `account` ADD `password_hash` TEXT')
        self.database.executemany(
            'UPDATE OR ROLLBACK `account` SET `password_hash` = :hash, `password` = NULL WHERE `id` = :id',
            password_hashes,
        )
        self.database.execute('ALTER TABLE `account` DROP COLUMN `password`')
        self.database.commit()
