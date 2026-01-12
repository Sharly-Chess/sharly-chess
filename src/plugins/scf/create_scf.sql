/* These SQL commands are used to create the SCF database. */

CREATE TABLE `player` (
    `scf_code` INTEGER NOT NULL,
    `last_name` TEXT NOT NULL,
    `first_name` TEXT,
    `gender` INTEGER NOT NULL,
    `federation` TEXT,
    `city` TEXT,
    `club` TEXT,
    `fide_id` INTEGER,
    `fide_rating` INTEGER,
    `year_of_birth` INTEGER
);
