from database.sqlite.migration import BaseMigration


class Migration(BaseMigration):
    def forward(self):
        self.database.execute(
            """
            UPDATE `prize_category` SET `prize_sharing` = 'NONE' WHERE (
               SELECT 1 FROM `prize`
               WHERE `prize_category_id` = `prize_category`.`id`
               AND `is_monetary` = 0
            )
            """
        )
        self.database.execute('ALTER TABLE `prize` ADD `type` TEXT')
        self.database.execute(
            """
            UPDATE `prize` SET `type` =
                CASE
                    WHEN `is_monetary` == 1 THEN 'MONETARY' else 'NON_MONETARY'
                END;
            """
        )
        self.database.execute('ALTER TABLE `prize` DROP COLUMN `is_monetary`')

    def backward(self):
        self.database.execute('ALTER TABLE `prize` ADD `is_monetary` INTEGER')
        self.database.execute(
            """
            UPDATE `prize` SET `is_monetary` =
                CASE
                    WHEN `type` == 'MONETARY' THEN 1 else 0
                END;
            """
        )
        self.database.execute('ALTER TABLE `prize` DROP COLUMN `type`')
