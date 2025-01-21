/* These SQL commands are used to create the FIDE database. */

CREATE TABLE `player` (
    `id` INTEGER NOT NULL,
    `id_number` INTEGER NOT NULL,
    `name` TEXT NOT NULL,
    `federation` TEXT NOT NULL,
    `sex` TEXT NOT NULL,
    `title` TEXT,
    `woman_title` TEXT,
    `other_title` TEXT,
    `standard_rating` INT NOT NULL,
    `rapid_rating` INT NOT NULL,
    `blitz_rating` INT NOT NULL,
    `standard_k_factor` INT NOT NULL,
    `rapid_k_factor` INT NOT NULL,
    `blitz_k_factor` INT NOT NULL,
    `year_of_birth` INT NOT NULL,
    PRIMARY KEY(`id` AUTOINCREMENT),
    UNIQUE(`id_number`)
);
