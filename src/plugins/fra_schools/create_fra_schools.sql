/* These SQL commands are used to create the FFE database. */

CREATE TABLE `department` (
    `id` TEXT NOT NULL,
    `name` TEXT NOT NULL,
    PRIMARY KEY(`id`)
);

CREATE TABLE `school` (
    `id` INTEGER NOT NULL,
    `code` TEXT NOT NULL,
    `name` TEXT NOT NULL,
    `postal_code` TEXT NOT NULL,
    `department` TEXT REFERENCES department(id),
    `city` TEXT NOT NULL,
    `type` TEXT NOT NULL,
    `private` INTEGER NOT NULL,
    PRIMARY KEY(`id` AUTOINCREMENT)
);

CREATE VIRTUAL TABLE school_fts USING fts5(
    search_text,
    content='school',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 1',
    prefix='2, 3',
);
