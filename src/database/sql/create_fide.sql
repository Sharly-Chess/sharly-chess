/* These SQL commands are used to create the FIDE database. */

CREATE TABLE `player` (
    `id` INTEGER NOT NULL,
    `fide_id` INTEGER NOT NULL,
    `last_name` TEXT NOT NULL,
    `first_name` TEXT,
    `federation` TEXT NOT NULL,
    `gender` INTEGER NOT NULL,
    `fide_title` INTEGER,
    `standard_rating` INTEGER NOT NULL,
    `rapid_rating` INTEGER NOT NULL,
    `blitz_rating` INTEGER NOT NULL,
    `year_of_birth` INTEGER NOT NULL,
    PRIMARY KEY(`id` AUTOINCREMENT)
);

CREATE INDEX "player_first_name" ON "player" (
    "first_name" COLLATE NOCASE
);

CREATE INDEX "player_last_name" ON "player" (
    "last_name" COLLATE NOCASE
);

CREATE INDEX "player_fide_id" ON "player" (
    "fide_id"
);