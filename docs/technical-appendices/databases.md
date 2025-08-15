# _Sharly Chess_ - Description of the databases

## _Sharly Chess_ configuration database (`events/.scc`)

### `info` (general application configuration)

> [!NOTE]
> :information_source: Table `info` contains only one line.

| Field                | Type      | Constraint | Description                                                                                                                  |
|----------------------|-----------|------------|------------------------------------------------------------------------------------------------------------------------------|
| `force_edit`         | `INTEGER` | NOT NULL   | Boolean:<br/>- `1`: Editing the configuration is mandatory;<br/>- `0`: Editing the configuration is possible but optional    |
| `console_log_level`  | `INTEGER` |            | The console logging level                                                                                                    |
| `console_color`      | `INTEGER` |            | Boolean:<br/>- `1`: Use colors on the console (default);<br/>- `0`: Do not use colors on the console                         |
| `console_show_date`  | `INTEGER` |            | Boolean:<br/>- `1`: Show the date and time on the console;<br/>- `0`: Do not show the date and time on the console (default) |
| `console_show_level` | `INTEGER` |            | Boolean:<br/>- `1`: Show the logging level on the console;<br/>- `0`: Do not show the logging level on the console (default) |
| `launch_browser`     | `INTEGER` |            | Boolean:<br/>- `1`: A browser is automatically opened (default);<br/>- `0`: No browser is opened                             |
| `federation`         | `TEXT`    |            | The default federation code for events                                                                                       |
| `locale`             | `TEXT`    |            | The default language used for users                                                                                          |
| `experimental`       | `INTEGER` |            | Boolean:<br/>- `1`: Experimental features are enabled;<br/>- `0`: Experimental features are disabled (default)               |

### `local_source_database` (local player databases)

| Field            | Type    | Constraint | Description                                                                          |
|------------------|---------|------------|--------------------------------------------------------------------------------------|
| `name`           | `TEXT`  | NOT NULL   | The database name                                                                    |
| `outdated_delay` | `TEXT`  | NOT NULL   | The auto-update delay (`disabled`, `daily`, `2days`, `3days`, `weekly`, `month_1st`) |
| `outdate_action` | `TEXT`  | NOT NULL   | The action to take when the database needs to be updated (`notif`, `auto_update`)    |
| `updated_at`     | `FLOAT` |            | The last update date for the database                                                |

### `metadata` (application metadata)

| Field       | Type   | Constraint                               | Description              |
|-------------|--------|------------------------------------------|--------------------------|
| `version`   | `TEXT` | NOT NULL                                 | The application version  |
| `migration` | `TEXT` | NOT NULL<br/>DEFAULT 'm000_no_migration' | The last database update |

### `plugin` (extensions)

| Field        | Type      | Constraint | Description                                                                           |
|--------------|-----------|------------|---------------------------------------------------------------------------------------|
| `name`       | `TEXT`    | NOT NULL   | The name of the extension                                                             |
| `is_enabled` | `INTEGER` | NOT NULL   | Boolean:<br/>- `1`: The extension is enabled;<br/>- `0`: The extension is not enabled |

## Event Database (`events/*.sce`)

``sce`` stands for **S**harly **C**hess **E**vent.

### `info` table (general information about the event)

> [!NOTE]
> :information_source:
> - The `info` table contains only one row.
> - The tournament's unique identifier is not stored in the database; it is retrieved from the event database filename.

| Field                            | Type      | Constraint                 | Ext        | Description                                                                                                                                                                                                              |
|----------------------------------|-----------|----------------------------|------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `name`                           | `TEXT`    | NOT NULL<br> DEFAULT '?'   |            | The name of the event                                                                                                                                                                                                    |
| `start`                          | `FLOAT`   | NOT NULL                   |            | The start date of the event (timestamp)                                                                                                                                                                                  |
| `stop`                           | `FLOAT`   | NOT NULL                   |            | The end date of the event (timestamp)                                                                                                                                                                                    |
| `public`                         | `INTEGER` |                            |            | Boolean:<br/>- `1`: the event is public (visible to users on the public interface);<br/>- `0`: the event is reserved for referees                                                                                        |
| `path`                           | `TEXT`    |                            |            | The relative or absolute path to the event's tournament Papi files                                                                                                                                                       |
| `hide_background_image`          | `INTEGER` |                            |            | Boolean:<br/>- `1`: a background image is displayed on the screens;<br/>- `0`: no background image is displayed                                                                                                          |
| `background_image`               | `TEXT`    |                            |            | A URL or relative path (in the `/custom` directory) to a local image (by default, no logo is used)                                                                                                                       |
| `background_color`               | `TEXT`    |                            |            | The background color of the event's screens in hexadecimal format '`#RRGGBB` (default `#E9ECEF`)                                                                                                                         |
| `record_illegal_moves`           | `INTEGER` |                            |            | The maximum number of illegal moves a player can record per round by default (this number can be changed for each tournament in the event) If this number is not specified, no legal moves can be recorded (default `0`) |
| `rules`                          | `TEXT`    |                            |            | The URL or server path to the event's tournament rules, in PDF format                                                                                                                                                    |
| `timer_colors`                   | `TEXT`    |                            |            | The default colors used for timers in JSON format (dictionary with keys `1'`, `2'`, and `3'`, each color is stored in hexadecimal format `#RRGGBB`)                                                                      |
| `timer_delays`                   | `TEXT`    |                            |            | The default delays used for timers in JSON format (dictionary with keys `1'`, `2'`, and `3'`, each delay is stored as an integer, in seconds)                                                                            |
| `message_text`                   | `TEXT`    |                            |            | The text of the event's alert messages (by default, no alert messages are displayed)                                                                                                                                     |
| `message_color`                  | `TEXT`    |                            |            | The color of the event's alert messages in hexadecimal format `#RRGGBB` (default `#FF0000`)                                                                                                                              |
| `message_background_color`       | `TEXT`    |                            |            | The background color of the event's alert messages in hexadecimal format `#RRGGBB` (default `#FFFF00`)                                                                                                                   |
| `federation`                     | `TEXT`    | NOT NULL<br/>DEFAULT 'NON' |            | The event's federation code                                                                                                                                                                                              |
| `deprecated_chessevent_user_id`  | `TEXT`    |                            |            | _Deprecated_                                                                                                                                                                                                             |
| `deprecated_chessevent_password` | `TEXT`    |                            |            | _Deprecated_                                                                                                                                                                                                             |
| `deprecated_chessevent_event_id` | `TEXT`    |                            |            | _Deprecated_                                                                                                                                                                                                             |
| `ffe_auto_upload`                | `INTEGER` | NOT NULL<br/>DEFAULT 0     |            | _TODO_                                                                                                                                                                                                                   |
| `ffe_auto_upload_delay`          | `INTEGER` |                            |            | _TODO_                                                                                                                                                                                                                   |
| `custom_exec_mode`               | `INTEGER` | NOT NULL<br/>DEFAULT 0     |            | Boolean:<br/>- `0`: the default execution mode is used (by default);<br/>- `1`: roles can be given to clients.                                                                                                           |

### `metadata` (event metadata)

| Field       | Type   | Constraint                               | Description                           |
|-------------|--------|------------------------------------------|---------------------------------------|
| `version`   | `TEXT` | NOT NULL                                 | The event database version            |
| `migration` | `TEXT` | NOT NULL<br/>DEFAULT 'm000_no_migration' | The last update of the event database |

### `plugin_metadata` (plugin metadata for the event)

| Field       | Type   | Constraint                               | Description                                        |
|-------------|--------|------------------------------------------|----------------------------------------------------|
| `name`      | `TEXT` | NOT NULL                                 | The name of the plugin                             |
| `version`   | `TEXT` | NOT NULL                                 | The database version of the plugin for the event   |
| `migration` | `TEXT` | NOT NULL<br/>DEFAULT 'm000_no_migration' | The latest extension database update for the event |

### `timer` (timer configurations)

| Field     | Type      | Constraint                                 | Ext | Description                                                                                                                        |
|-----------|-----------|--------------------------------------------|-----|------------------------------------------------------------------------------------------------------------------------------------|
| `id`      | `INTEGER` | NOT NULL<br/>PRIMARY KEY<br/>AUTOINCREMENT |     | The stopwatch identifier                                                                                                           |
| `uniq_id` | `TEXT`    | NOT NULL<br/>UNIQUE                        |     | The unique text identifier of the stopwatch                                                                                        |
| `colors`  | `TEXT`    |                                            |     | The colors used in JSON format (dictionary with keys `1'`, `2'`, and `3'`, each color is stored in hexadecimal format ``#RRGGBB``) |
| `delays`  | `TEXT`    |                                            |     | The delays used in JSON format (dictionary with keys `'1'`, `'2'` and `'3'`, each delay is stored as an integer, in seconds)       |

### `timer_hour` (timer hours)

| Field         | Type      | Constraint                                 | Ext | Description                                                                                                                           |
|---------------|-----------|--------------------------------------------|-----|---------------------------------------------------------------------------------------------------------------------------------------|
| `id`          | `INTEGER` | NOT NULL<br/>PRIMARY KEY<br/>AUTOINCREMENT |     | The timer ID                                                                                                                          |
| `uniq_id`     | `TEXT`    | NOT NULL                                   |     | The unique text ID of the timer (if the field is a positive integer, the timer is identified as the start of the corresponding round) |
| `timer_id`    | `INTEGER` | NOT NULL<br>REFERENCES `timer`(`id`)       |     | The timer ID                                                                                                                          |
| `order`       | `INTEGER` | NOT NULL                                   |     | The order of the timer relative to the other times in its timer                                                                       |
| `date_str`    | `TEXT`    |                                            |     | The date of the schedule in YYYY-MM-DD format                                                                                         |
| `time_str`    | `TEXT`    |                                            |     | The time of the schedule in hh:mm format                                                                                              |
| `text_before` | `TEXT`    |                                            |     | The text to display on the timer before the schedule                                                                                  |
| `text_after`  | `TEXT`    |                                            |     | The text to display on the timer after the schedule                                                                                   |
|               |           | UNIQUE(`uniq_id`, `timer_id`)              |     |                                                                                                                                       |

### `tournament` (tournaments)

| Field                                     | Type      | Constraint                                 | Ext        | Description                                                                                                                                                |
|-------------------------------------------|-----------|--------------------------------------------|------------|------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `id`                                      | `INTEGER` | NOT NULL<br/>PRIMARY KEY<br/>AUTOINCREMENT |            | The tournament ID                                                                                                                                          |
| `uniq_id`                                 | `TEXT`    | NOT NULL                                   |            | The unique text ID of the tournament                                                                                                                       |
| `name`                                    | `TEXT`    | NOT NULL                                   |            | The tournament name                                                                                                                                        |
| `location`                                | `TEXT`    |                                            |            | The location of the tournament (by default the location of the event)                                                                                      |
| `start`                                   | `TEXT`    |                                            |            | The start date of the tournament (timestamp, by default the start date of the event)                                                                       |
| `stop`                                    | `TEXT`    |                                            |            | The stop date of the tournament (timestamp, by default the stop date of the event)                                                                         |
| `stop`                                    | `FLOAT`   | NOT NULL                                   |            | The end date of the event (timestamp)                                                                                                                      |
| `time_control_initial_time`               | `INTEGER` |                                            |            | The initial time on the clock in seconds (can be zero if incremented)                                                                                      |
| `time_control_increment`                  | `INTEGER` |                                            |            | The time increment gained by the players on each shot                                                                                                      |
| `time_control_handicap_penalty_step`      | `INTEGER` |                                            |            | The time subtracted from the higher-ranked player, in seconds (this time is multiplied by the number of increments of difference between the two players)  |
| `time_control_handicap_penalty_value`     | `INTEGER` |                                            |            | The number of points of difference between the players' rankings used to calculate the number of penalties applied to the higher-ranked player             |
| `time_control_handicap_min_time`          | `INTEGER` |                                            |            | The minimum time that will be granted to the highest-ranked player, even if the difference in ranking is very significant                                  |
| `record_illegal_moves`                    | `INTEGER` |                                            |            | The maximum number of illegal moves that can be recorded for a player per round If this number is not specified, the event's default configuration is used |
| `rules`                                   | `TEXT`    |                                            |            | The URL or server path to the tournament rules, in PDF format (by default, the event rules)                                                                |
| `check_in_open`                           | `INTEGER` |                                            |            | Boolean:<br/>- `1`: Checking is open<br/>- `0`: Checking is closed                                                                                         |
| `last_update`                             | `FLOAT`   | NOT NULL                                   |            | The last date the tournament was modified                                                                                                                  |
| `last_player_update`.                     | `FLOAT`   | NOT NULL<br/>DEFAULT 0.0                   |            | The last date a player associated with this tournament was modified                                                                                        |
| `last_pairing_update`                     | `FLOAT`   | NOT NULL<br/>DEFAULT 0.0                   |            | The last date a pairing associated with this tournament score was modified                                                                                 |
| `first_board_number`                      | `INTEGER` |                                            |            | The first board number                                                                                                                                     |
| `paired_bye_result`                       | `INTEGER` |                                            |            | Result awarded to bye players                                                                                                                              |
| `max_byes`                                | `INTEGER` |                                            |            | The maximum number of byes a player can claim                                                                                                              |
| `last_rounds_no_byes`                     | `INTEGER` |                                            |            | The number of final rounds for which players cannot take byes                                                                                              |
| `tie_breaks`                              | `TEXT`    |                                            |            | The tie-breaks used in JSON format (list of dictionaries in the format {'type': str, 'options': dict[str,any]})                                            |
| `rounds`                                  | `INTEGER` | NOT NULL<br/>DEFAULT 1                     |            | The tournament's round count                                                                                                                               |
| `rating`                                  | `INTEGER` | NOT NULL<br/>DEFAULT 1                     |            | The tournament's rating:<br/>- `1`: Estimated<br/>- `2`: National<br/>- `3`: Fide                                                                          |
| `pairing`                                 | `TEXT`    |                                            |            | The tournament's pairing as a string                                                                                                                       |
| `pairing_settings`                        | `TEXT`    |                                            |            | The tournament's pairing settings, in JSON format                                                                                                          |
| `current_round`                           | `INTEGER` |                                            |            | The tournament's current round                                                                                                                             |
| `three_points_for_a_win`                  | `INTEGER` | NOT NULL<br/>DEFAULT 0.0                   |            | Boolean:<br/>- `0`: 1 point for a win<br/>- `1`: 3 points for a win                                                                                        |
| `deprecated_chessevent_user_id`           | `TEXT`    |                                            | chessevent | _Deprecated_                                                                                                                                               |
| `deprecated_chessevent_password`          | `TEXT`    |                                            | chessevent | _Deprecated_                                                                                                                                               |
| `deprecated_chessevent_event_id`          | `TEXT`    |                                            | chessevent | _Deprecated_                                                                                                                                               |
| `deprecated_chessevent_tournament_name`   | `TEXT`    |                                            | chessevent | _Deprecated_                                                                                                                                               |
| `deprecated_last_chessevent_download_md5` | `TEXT`    |                                            | chessevent | _Deprecated_                                                                                                                                               |
| `ffe_id`                                  | `INTEGER` |                                            | ffe        | The tournament's approval number on the FFE federal website                                                                                                |
| `ffe_password`                            | `TEXT`    |                                            | ffe        | The tournament access code on the FFE federal website (consisting of 10 capital letters)                                                                   |
| `ffe_last_upload`                         | `FLOAT`   | NOT NULL<br/>DEFAULT 0.0                   | ffe        | The date the tournament was last uploaded to the FFE federal website                                                                                       |
| `ffe_last_rules_upload`                   | `FLOAT`   | NOT NULL<br/>DEFAULT 0.0                   | ffe        | The date of the last sending of the tournament rules to the FFE federal website                                                                            |

### `player` (players)

| Field           | Type      | Constraint                                 | Ext | Description                                                                                             |
|-----------------|-----------|--------------------------------------------|-----|---------------------------------------------------------------------------------------------------------|
| `id`            | `INTEGER` | NOT NULL<br/>PRIMARY KEY<br/>AUTOINCREMENT |     | The player ID                                                                                           |
| `last_name`     | `TEXT`    | NOT NULL                                   |     | The player's last name                                                                                  |
| `first_name`    | `TEXT`    |                                            |     | The player's first name                                                                                 |
| `date_of_birth` | `TEXT`    |                                            |     | The player's date of birth in YYYY-MM-DD format                                                         |
| `gender`        | `INTEGER` | NOT NULL                                   |     | The player's gender (1: Male, 2: Female, 9: Other)                                                      |
| `mail`          | `TEXT`    |                                            |     | The player's email address                                                                              |
| `phone`         | `TEXT`    |                                            |     | The player's phone number                                                                               |
| `comment`       | `TEXT`    |                                            |     | Comments about the player                                                                               |
| `owed`          | `FLOAT`   | NOT NULL                                   |     | Amount of money owed by the player                                                                      |
| `paid`          | `FLOAT`   | NOT NULL                                   |     | Amount of money paid by the player                                                                      |
| `title`         | `INTEGER` | NOT NULL                                   |     | The player's chess title                                                                                |
| `ratings`       | `TEXT`    | NOT NULL                                   |     | The player's ratings in JSON format                                                                     |
| `fide_id`       | `INTEGER` |                                            |     | The player's FIDE ID                                                                                    |
| `federation`    | `TEXT`    |                                            |     | The player's federation code                                                                            |
| `club`          | `TEXT`    |                                            |     | The player's chess club                                                                                 |
| `fixed`         | `INTEGER` |                                            |     | Boolean: whether the player's is assigned a fixed table                                                 |
| `check_in`      | `INTEGER` | NOT NULL<br/>DEFAULT 0                     |     | Boolean: whether the player has checked in                                                              |
| `plugin_data`   | `TEXT`    | NOT NULL                                   |     | Additional data used by plugins, in JSON format                                                         |

### `tournament_player` (tournament player associations)

| Field            | Type      | Constraint                                                         | Ext | Description                               |
|------------------|-----------|--------------------------------------------------------------------|-----|-------------------------------------------|
| `tournament_id`  | `INTEGER` | NOT NULL<br/>REFERENCES `tournament`(`id`)<br/>PRIMARY KEY         |     | The tournament ID                         |
| `player_id`      | `INTEGER` | NOT NULL<br/>REFERENCES `player`(`id`)<br/>PRIMARY KEY             |     | The player ID                             |
| `pairing_number` | `INTEGER` |                                                                    |     | The player's pairing number in tournament |

### `board` (chess boards)

| Field                | Type      | Constraint                                                    | Ext | Description                                   |
|----------------------|-----------|---------------------------------------------------------------|-----|-----------------------------------------------|
| `id`                 | `INTEGER` | NOT NULL<br/>PRIMARY KEY<br/>AUTOINCREMENT                    |     | The board ID                                  |
| `white_player_id`    | `INTEGER` | NOT NULL<br/>REFERENCES `player`(`id`)                        |     | The white player ID                           |
| `black_player_id`    | `INTEGER` | REFERENCES `player`(`id`)                                     |     | The black player ID (can be NULL for byes)    |
| `index`              | `INTEGER` | NOT NULL                                                      |     | The board number/index                        |
| `last_result_update` | `FLOAT`   |                                                               |     | Timestamp of the last result update for board |

### `pairing` (tournament pairings and results)

| Field           | Type      | Constraint                                                                           | Ext | Description                                             |
|-----------------|-----------|--------------------------------------------------------------------------------------|-----|---------------------------------------------------------|
| `tournament_id` | `INTEGER` | NOT NULL<br/>REFERENCES `tournament`(`id`)<br/>PRIMARY KEY                           |     | The tournament ID                                       |
| `player_id`     | `INTEGER` | NOT NULL<br/>REFERENCES `player`(`id`)<br/>PRIMARY KEY                               |     | The player ID                                           |
| `round`         | `INTEGER` | NOT NULL<br/>PRIMARY KEY                                                             |     | The round number                                        |
| `result`        | `INTEGER` | NOT NULL                                                                             |     | The game result for the player                          |
| `board_id`      | `INTEGER` | REFERENCES `board`(`id`)                                                             |     | The board ID where the game is played                   |
| `illegal_moves` | `INTEGER` | NOT NULL<br/>DEFAULT 0                                                               |     | Number of illegal moves made by the player in the round |

### `screen` (screens)

| Field                    | Type      | Constraint                                 | Ext | Description                                                                                                                                                                                                       |
|--------------------------|-----------|--------------------------------------------|-----|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `id`                     | `INTEGER` | NOT NULL<br/>PRIMARY KEY<br/>AUTOINCREMENT |     | The screen ID                                                                                                                                                                                                     |
| `uniq_id`                | `TEXT`    | NOT NULL<br/>UNIQUE                        |     | The unique text ID of the screen                                                                                                                                                                                  |
| `type`                   | `TEXT`    | NOT NULL                                   |     | The screen type:<br/>- `input`: results entry<br/>- `boards`: pairings by chessboard<br/>- `players`: pairings in alphabetical order<br/>- `results`: latest results<br/>- `image`: image                         |
| `public`                 | `INTEGER` |                                            |     | Boolean:<br/>- `1`: the screen is public (visible to users on the public interface);<br/>- `0`: the screen is reserved for referees                                                                               |
| `name`                   | `TEXT`    |                                            |     | The name of the screen                                                                                                                                                                                            |
| `columns`                | `INTEGER` |                                            |     | The number of columns on the screen                                                                                                                                                                               |
| `menu_link`              | `INTEGER` |                                            |     | Boolean:<br/>- `NULL` if `type` is `image`;<br/>- `1`: a link to this screen can be displayed from other screens;<br/>- `0`: no link to this screen will ever be displayed                                        |
| `menu_text`              | `TEXT`    |                                            |     | `NULL` if `type` is `image`, otherwise the text of the hyperlink to the screen, used on other screens                                                                                                             |
| `menu`                   | `TEXT`    |                                            |     | `NULL` if `type` is `image`, otherwise the menu to display on the screen (hyperlinks to other screens)                                                                                                            |
| `timer_id`               | `INTEGER` | REFERENCES `timer`(`id`)                   |     | The timer ID                                                                                                                                                                                                      |
| `input_exit_button`      | `INTEGER` |                                            |     | Boolean:<br/>- `NULL` if `type` is different from `input`;<br/>- `1`: a button to exit the page is displayed;<br/>- `0`: the button is not displayed                                                              |
| `players_show_unpaired`  | `INTEGER` |                                            |     | Boolean:<br/>- `NULL` if `type` is different from `players`;<br/>- `0`: non-paired players are hidden;<br/>- `1`: non-paired players are shown                                                                    |
| `players_show_opponent`  | `INTEGER` |                                            |     | Boolean:<br/>- `NULL` if `type` is different from `players`;<br/>- `0`: players' opponent are hidden;<br/>- `0`: players' opponent are shown                                                                      |
| `results_limit`          | `INTEGER` |                                            |     | - `NULL` if `type` is different from `results`;<br/>- `0`: all recent results are shown;<br/>- positive integer: the maximum number of results shown on the screen                                                |
| `results_max_age`        | `INTEGER` |                                            |     | - `NULL` if `type` is different from `results`;<br/>- `NULL` or positive integer: the maximum age of results displayed on the screen (in minutes, default 60)                                                     |
| `results_tournament_ids` | `TEXT`    |                                            |     | - `NULL` if `type` is not equal to `results`;<br/>- The list of tournament IDs for which results are displayed on the screen, in JSON format (if the list is empty, the results of all tournaments are displayed) |
| `background_image`       | `TEXT`    |                                            |     | - `NULL` if `type` is not equal to `image`;<br/>- The URL of the image to display                                                                                                                                 |
| `background_color`       | `TEXT`    |                                            |     | - `NULL` if `type` is not equal to `image`;<br/>- The background color of the image, in hexadecimal format `#RRGGBB`                                                                                              |
| `ranking_crosstable`     | `INTEGER` |                                            |     | Boolean:<br/>- `1`: American grid;<br/>- `0`: simple ranking                                                                                                                                                      |
| `ranking_round`          | `INTEGER` |                                            |     | The number of the round to display (by default the last round played)                                                                                                                                             |
| `ranking_min_points`     | `INTEGER` |                                            |     | The minimum number of points of the displayed players                                                                                                                                                             |
| `ranking_max_points`     | `INTEGER` |                                            |     | The maximum number of points for the displayed players                                                                                                                                                            |
| `ranking_crosstable`     | `INTEGER` |                                            |     | Boolean:<br/>- `1`: American grid;<br/>- `0`: Simple ranking                                                                                                                                                      |
| `font_size`              | `INTEGER` |                                            |     | The font size in percentage (default 100%)                                                                                                                                                                        |
| `message_default`        | `INTEGER` | NOT NULL<br/>DEFAULT 1                     |     | Boolean:<br/>- `1`: The event alert message (or the rotating screen, if applicable) is used;<br/>- `0`: The screen alert message is used instead of the event alert message                                       |
| `message_text`           | `TEXT`    |                                            |     | The text of the screen's alert message (by default, no alert message is displayed)                                                                                                                                |
| `last_update`            | `FLOAT`   | NOT NULL                                   |     | The date the screen was last modified                                                                                                                                                                             |

### `screen_set` (screen sets)

| Field              | Type      | Constraint                                 | Ext | Description                                                   |
|--------------------|-----------|--------------------------------------------|-----|---------------------------------------------------------------|
| `id`               | `INTEGER` | NOT NULL<br/>PRIMARY KEY<br/>AUTOINCREMENT |     | The screen ID                                                 |
| `screen_id`        | `TEXT`    | NOT NULL<br/>REFERENCES `screen`(`id`)     |     | The unique text ID of the screen                              |
| `tournament_id`    | `TEXT`    | NOT NULL<br/>REFERENCES `tournament`(`id`) |     | The tournament ID                                             |
| `name`             | `TEXT`    |                                            |     | The name of the set                                           |
| `order`            | `INTEGER` | NOT NULL                                   |     | The order of the set relative to other sets on its screen     |
| `first`            | `INTEGER` |                                            |     | The number of the first element (board or player) to consider |
| `last`             | `INTEGER` |                                            |     | The number of the last element (board or player) to consider  |
| `fixed_boards_str` | `TEXT`    |                                            |     | Board numbers separated by commas                             |
| `last_update`      | `FLOAT`   | NOT NULL                                   |     | The date the set was last modified                            |

### `family` (screen families)

| Field                   | Type      | Constraint                                 | Ext | Description                                                                                                                                                                                                                      |
|-------------------------|-----------|--------------------------------------------|-----|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `id`                    | `INTEGER` | NOT NULL<br/>PRIMARY KEY<br/>AUTOINCREMENT |     | The family ID                                                                                                                                                                                                                    |
| `uniq_id`               | `TEXT`    | NOT NULL<br/>UNIQUE                        |     | The unique text ID of the family                                                                                                                                                                                                 |
| `type`                  | `TEXT`    | NOT NULL                                   |     | The screen type:<br/>- `input`: results entry<br/>- `boards`: pairings by chessboard<br/>- `players`: pairings in alphabetical order<br/>- `results`: latest results<br/>- `image`: image                                        |
| `public`                | `INTEGER` |                                            |     | Boolean:<br/>- `1`: the family is public (visible to users on the public interface);<br/>- `0`: the family is reserved for referees                                                                                              |
| `name`                  | `TEXT`    |                                            |     | The name of the family                                                                                                                                                                                                           |
| `columns`               | `INTEGER` |                                            |     | The number of columns in the family's screens                                                                                                                                                                                    |
| `menu_link`             | `INTEGER` | NOT NULL                                   |     | Boolean:<br/>- `1`: a link to the family's screens can be displayed from other screens;<br/>- `0`: no link to the family's screens will ever be displayed                                                                        |
| `menu_text`             | `TEXT`    | NOT NULL                                   |     | The text of the hyperlink to the family's screens, used on other screens                                                                                                                                                         |
| `menu`                  | `TEXT`    | NOT NULL                                   |     | The menu to display on the family's screens (hyperlinks to other screens)                                                                                                                                                        |
| `timer_id`              | `INTEGER` | REFERENCES `timer`(`id`)                   |     | The ID of the timer used on the family's screens                                                                                                                                                                                 |
| `tournament_id`         | `INTEGER` | REFERENCES `tournament`(`id`)              |     | The ID of the tournament in the family                                                                                                                                                                                           |
| `input_exit_button`     | `INTEGER` |                                            |     | Boolean:<br/>- `NULL` if `type` is different from `input`;<br/>- `1`: a button to exit the page is displayed;<br/>- `0`: the button is not displayed                                                                             |
| `players_show_unpaired` | `INTEGER` |                                            |     | Boolean:<br/>- `NULL` if `type` is different from `players`;<br/>- `0`: non-paired players are hidden;<br/>- `1`: non-paired players are shown                                                                                   |
| `players_show_opponent` | `INTEGER` |                                            |     | Boolean:<br/>- `NULL` if `type` is different from `players`;<br/>- `0`: players' opponent are hidden;<br/>- `0`: players' opponent are shown                                                                                     |
| `first`                 | `INTEGER` |                                            |     | The number of the first element (board or player) to consider                                                                                                                                                                    |
| `last`                  | `INTEGER` |                                            |     | The number of the last element (board or player) to consider                                                                                                                                                                     |
| `range`                 | `TEXT`    |                                            |     | The range of screens to generate, for example `4-6` (by default, all screens in the family are generated)                                                                                                                        |
| `parts`                 | `INTEGER` |                                            |     | The number of screens in the family (the number of elements per screen is calculated automatically)                                                                                                                              |
| `number`                | `INTEGER` |                                            |     | The number of elements (boards or players) per screen (the number of screens is calculated automatically)                                                                                                                        |
| `message_default`       | `INTEGER` | NOT NULL<br/>DEFAULT 1                     |     | Boolean:<br/>- `1`: The event alert message (or the rotating screen, if applicable) is used for the screens in the family;<br/>- `0`: The alert message for the screens in the family is used instead of the event alert message |
| `message_text`          | `TEXT`    |                                            |     | The text of the screen's alert message (by default, no alert message is displayed)                                                                                                                                               |
| `last_update`           | `FLOAT`   | NOT NULL                                   |     | The last date the screen was modified                                                                                                                                                                                            |

### `rotator` (rotating screens)

| Field             | Type      | Constraint                                 | Ext | Description                                                                                                                                                                                                  |
|-------------------|-----------|--------------------------------------------|-----|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `id`              | `INTEGER` | NOT NULL<br/>PRIMARY KEY<br/>AUTOINCREMENT |     | The rotating screen's identifier                                                                                                                                                                             |
| `uniq_id`         | `TEXT`    | NOT NULL<br/>UNIQUE                        |     | The unique text identifier of the rotating screen                                                                                                                                                            |
| `public`          | `INTEGER` |                                            |     | Boolean:<br/>- `1`: The rotating screen is public (visible to users on the public interface);<br/>- `0`: The rotating screen is reserved for referees                                                        |
| `screen_ids`      | `TEXT`    |                                            |     | The list of screens to display, in JSON format                                                                                                                                                               |
| `family_ids`      | `TEXT`    |                                            |     | The list of screen families to display, in JSON format                                                                                                                                                       |
| `delay`           | `INTEGER` |                                            |     | The screen rotation delay in seconds, optional (default 15)                                                                                                                                                  |
| `message_default` | `INTEGER` | NOT NULL<br/>DEFAULT 1                     |     | Boolean:<br/>- `1`: The event alert message is used (unless a message is defined for the screens);<br/>- `0`: The alert message for the rotating screen's screens is used instead of the event alert message |
| `message_text`    | `TEXT`    |                                            |     | The screen's alert message text (by default, no alert message is displayed)                                                                                                                                  |

### `display_controller` (display controllers)

| Field        | Type      | Constraint                                 | Ext | Description                                                                                                                           |
|--------------|-----------|--------------------------------------------|-----|---------------------------------------------------------------------------------------------------------------------------------------|
| `id`         | `INTEGER` | NOT NULL<br/>PRIMARY KEY<br/>AUTOINCREMENT |     | The display controller ID                                                                                                             |
| `uniq_id`    | `TEXT`    | NOT NULL<br/>UNIQUE                        |     | The unique text ID of the display controller                                                                                          |
| `name`       | `TEXT`    | NOT NULL                                   |     | The display controller name                                                                                                           |
| `public`     | `INTEGER` |                                            |     | Boolean:<br/>- `1`: the controller is public (visible to users on the public interface);<br/>- `0`: the controller is for referees    |
| `screen_id`  | `INTEGER` | REFERENCES `screen`(`id`)                  |     | The screen ID to display                                                                                                              |
| `rotator_id` | `INTEGER` | REFERENCES `rotator`(`id`)                 |     | The rotator ID to display                                                                                                             |
| `last_update`| `FLOAT`   |                                            |     | The date the controller was last updated                                                                                              |

### `prize_group` (prize groups)

| Field           | Type      | Constraint                                                | Ext | Description           |
|-----------------|-----------|-----------------------------------------------------------|-----|-----------------------|
| `id`            | `INTEGER` | NOT NULL<br/>PRIMARY KEY<br/>AUTOINCREMENT<br/>UNIQUE     |     | The prize group ID    |
| `tournament_id` | `INTEGER` | NOT NULL<br/>REFERENCES `tournament`(`id`)                |     | The tournament ID     |
| `name`          | `TEXT`    | NOT NULL                                                  |     | The prize group name  |

### `prize_category` (prize categories)

| Field               | Type      | Constraint                                                | Ext | Description                                       |
|---------------------|-----------|-----------------------------------------------------------|-----|---------------------------------------------------|
| `id`                | `INTEGER` | NOT NULL<br/>PRIMARY KEY<br/>AUTOINCREMENT<br/>UNIQUE     |     | The prize category ID                             |
| `prize_group_id`    | `INTEGER` | NOT NULL<br/>REFERENCES `prize_group`(`id`)               |     | The prize group ID                                |
| `name`              | `TEXT`    | NOT NULL                                                  |     | The prize category name                           |
| `prize_sharing`     | `TEXT`    | NOT NULL                                                  |     | How prizes are shared in this category            |
| `sharing_threshold` | `FLOAT`   |                                                           |     | The threshold for prize sharing                   |
| `is_main`           | `INTEGER` | NOT NULL<br/>DEFAULT 0                                    |     | Boolean: whether this is the main prize category  |
| `index`             | `INTEGER` | NOT NULL                                                  |     | The ordering index of the category                |

### `prize_criterion` (prize criteria)

| Field               | Type      | Constraint                                                | Ext | Description                        |
|---------------------|-----------|-----------------------------------------------------------|-----|------------------------------------|
| `id`                | `INTEGER` | NOT NULL<br/>PRIMARY KEY<br/>AUTOINCREMENT<br/>UNIQUE     |     | The prize criterion ID             |
| `prize_category_id` | `INTEGER` | NOT NULL<br/>REFERENCES `prize_category`(`id`)            |     | The prize category ID              |
| `type`              | `TEXT`    | NOT NULL                                                  |     | The criterion type                 |
| `options`           | `TEXT`    |                                                           |     | Criterion options in JSON format   |

### `prize` (prizes)

| Field               | Type      | Constraint                                                | Ext | Description                               |
|---------------------|-----------|-----------------------------------------------------------|-----|-------------------------------------------|
| `id`                | `INTEGER` | NOT NULL<br/>PRIMARY KEY<br/>AUTOINCREMENT<br/>UNIQUE     |     | The prize ID                              |
| `prize_category_id` | `INTEGER` | NOT NULL<br/>REFERENCES `prize_category`(`id`)            |     | The prize category ID                     |
| `value`             | `FLOAT`   | NOT NULL<br/>DEFAULT 0.0                                  |     | The monetary value of the prize           |
| `is_monetary`       | `INTEGER` | NOT NULL<br/>DEFAULT 1                                    |     | Boolean: whether the prize is monetary    |
| `description`       | `TEXT`    |                                                           |     | The prize description                     |
