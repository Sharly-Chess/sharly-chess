/* These SQL commands are used to create the FFE database. */

CREATE TABLE `player` (
    `id` INTEGER NOT NULL,
    `ffe_id` INTEGER NOT NULL,
    `last_name` TEXT NOT NULL,
    `first_name` TEXT,
    `gender` INTEGER NOT NULL,
    `ffe_licence_number` TEXT,
    `ffe_licence` INTEGER NOT NULL,
    `federation` TEXT NOT NULL,
    `league` TEXT,
    `city` TEXT,
    `club` TEXT,
    `fide_id` INTEGER,
    `fide_title` INTEGER NOT NULL,
    `standard_rating` INTEGER NOT NULL,
    `rapid_rating` INTEGER NOT NULL,
    `blitz_rating` INTEGER NOT NULL,
    `standard_rating_type` INTEGER NOT NULL,
    `rapid_rating_type` INTEGER NOT NULL,
    `blitz_rating_type` INTEGER NOT NULL,
    `date_of_birth` INTEGER,
    PRIMARY KEY(`id` AUTOINCREMENT)
);

CREATE INDEX "player_last_name" ON "player" (
    "last_name" COLLATE NOCASE
);

CREATE INDEX "player_first_name" ON "player" (
    "first_name" COLLATE NOCASE
);

CREATE INDEX "player_fide_id" ON "player" (
    "fide_id"
);

CREATE INDEX "player_ffe_licence" ON "player" (
    "ffe_licence_number"
);
