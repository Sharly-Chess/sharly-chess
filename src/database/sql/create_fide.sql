/* These SQL commands are used to create the FIDE database. */

CREATE TABLE `player` (
    `id` INTEGER NOT NULL,
    `fide_id` INTEGER NOT NULL,
    `last_name` TEXT NOT NULL,
    `first_name` TEXT,
    `federation` TEXT NOT NULL,
    `gender` TEXT NOT NULL,
    `fide_title` TEXT,
    `standard_rating` INTEGER NOT NULL,
    `rapid_rating` INTEGER NOT NULL,
    `blitz_rating` INTEGER NOT NULL,
    `year_of_birth` INTEGER NOT NULL,
    `k_standard` INTEGER NOT NULL,
    `k_rapid` INTEGER NOT NULL,
    `k_blitz` INTEGER NOT NULL,
    PRIMARY KEY(`id` AUTOINCREMENT),
    UNIQUE(`fide_id`)
);

CREATE TABLE `arbiter` (
    `player_fide_id` INTEGER NOT NULL,
    `fide_arbiter_title` TEXT NOT NULL,
    UNIQUE(`player_fide_id`),
    FOREIGN KEY (`player_fide_id`) REFERENCES `player`(`fide_id`)
);
