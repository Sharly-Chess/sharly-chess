# _Sharly Chess_ - Description of the databases

## _Sharly Chess_ configuration database (`events/.scc`)

### `info` (general application configuration)

> [!NOTE]
> :information_source: Table `info` contains only one line.

| Field                | Type      | Constraint           | Description                                                                                                                  |
|----------------------|-----------|----------------------|------------------------------------------------------------------------------------------------------------------------------|
| `force_edit`         | `INTEGER` | NOT NULL             | Boolean:<br/>- `1`: Editing the configuration is mandatory;<br/>- `0`: Editing the configuration is possible but optional    |
| `console_log_level`  | `INTEGER` |                      | The console logging level                                                                                                    |
| `console_color`      | `INTEGER` |                      | Boolean:<br/>- `1`: Use colors on the console (default);<br/>- `0`: Do not use colors on the console                         |
| `console_show_date`  | `INTEGER` |                      | Boolean:<br/>- `1`: Show the date and time on the console;<br/>- `0`: Do not show the date and time on the console (default) |
| `console_show_level` | `INTEGER` |                      | Boolean:<br/>- `1`: Show the logging level on the console;<br/>- `0`: Do not show the logging level on the console (default) |
| `launch_browser`     | `INTEGER` |                      | Boolean:<br/>- `1`: A browser is automatically opened (default);<br/>- `0`: No browser is opened                             |
| `federation`         | `TEXT`    |                      | The default federation code for events                                                                                       |
| `locale`             | `TEXT`    |                      | The default language used for users                                                                                          |
| `experimental`       | `INTEGER` |                      | Boolean:<br/>- `1`: Experimental features are enabled;<br/>- `0`: Experimental features are disabled (default)               |

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

### `Plugin` (extensions)

| Field     | Type      | Constraint | Description                                                                           |
|-----------|-----------|------------|---------------------------------------------------------------------------------------|
| `name`    | `TEXT`    | NOT NULL   | The name of the extension                                                             |
| `enabled` | `INTEGER` | NOT NULL   | Boolean:<br/>- `1`: The extension is enabled;<br/>- `0`: The extension is not enabled |

## Event Database (`events/*.sce`)

``sce`` stands for **S**harly **C**hess **E**vent.

### `info` table (general information about the event)

> [!NOTE]
> :information_source:
> - The `info` table contains only one row.
> - The tournament's unique identifier is not stored in the database; it is retrieved from the event database filename.

| Field                      | Type      | Constraint                | Ext        | Description                                                                                                                                                                                                              |
|----------------------------|-----------|---------------------------|------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `name`                     | `TEXT`    | NOT NULL<br> DEFAULT '?'  |            | The name of the event                                                                                                                                                                                                    |
| `start`                    | `FLOAT`   | NOT NULL                  |            | The start date of the event (timestamp)                                                                                                                                                                                  |
| `stop`                     | `FLOAT`   | NOT NULL                  |            | The end date of the event (timestamp)                                                                                                                                                                                    |
| `public`                   | `INTEGER` |                           |            | Boolean:<br/>- `1`: the event is public (visible to users on the public interface);<br/>- `0`: the event is reserved for referees                                                                                        |
| `path`                     | `TEXT`    |                           |            | The relative or absolute path to the event's tournament Papi files                                                                                                                                                       |
| `hide_background_image`    | `INTEGER` |                           |            | Boolean:<br/>- `1`: a background image is displayed on the screens;<br/>- `0`: no background image is displayed                                                                                                          |
| `background_image`         | `TEXT`    |                           |            | A URL or relative path (in the `/custom` directory) to a local image (by default, no logo is used)                                                                                                                       |
| `background_color`         | `TEXT`    |                           |            | The background color of the event's screens in hexadecimal format '`#RRGGBB` (default `#E9ECEF`)                                                                                                                         |
| `record_illegal_moves`     | `INTEGER` |                           |            | The maximum number of illegal moves a player can record per round by default (this number can be changed for each tournament in the event) If this number is not specified, no legal moves can be recorded (default `0`) |
| `rules`                    | `TEXT`    |                           |            | The URL or server path to the event's tournament rules, in PDF format                                                                                                                                                    |
| `timer_colors`             | `TEXT`    |                           |            | The default colors used for timers in JSON format (dictionary with keys `1'`, `2'`, and `3'`, each color is stored in hexadecimal format `#RRGGBB`)                                                                      |
| `timer_delays`             | `TEXT`    |                           |            | The default delays used for timers in JSON format (dictionary with keys `1'`, `2'`, and `3'`, each delay is stored as an integer, in seconds)                                                                            |
| `message_text`             | `TEXT`    |                           |            | The text of the event's alert messages (by default, no alert messages are displayed)                                                                                                                                     |
| `message_color`            | `TEXT`    |                           |            | The color of the event's alert messages in hexadecimal format `#RRGGBB` (default `#FF0000`)                                                                                                                              |
| `message_background_color` | `TEXT`    |                           |            | The background color of the event's alert messages in hexadecimal format `#RRGGBB` (default `#FFFF00`)                                                                                                                   |
| `last_update`              | `FLOAT`   | NOT NULL                  |            | The date the event was last updated (timestamp)                                                                                                                                                                          |
| `federation`               | `TEXT`    | NOT NULL<br/>DEFAULT 'NO' |            | The event's federation code                                                                                                                                                                                              |
| `custom_exec_mode`         | `INTEGER` | NOT NULL                  |            | Boolean:<br/>- `0`: use the standard execution mode;<br/>- `0`: use the custom execution mode                                                                                                                            |
| `chessevent_user_id`       | `TEXT`    |                           | chessevent | The default login ID for the _ChessEvent_ platform                                                                                                                                                                       |
| `chessevent_password`      | `TEXT`    |                           | chessevent | The default password for the _ChessEvent_ platform                                                                                                                                                                       |
| `chessevent_event_id`      | `TEXT`    |                           | chessevent | The default login ID for the _ChessEvent_ event on the platform                                                                                                                                                          |

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

| Field                                 | Type      | Constraint                                 | Ext        | Description                                                                                                                                                |
|---------------------------------------|-----------|--------------------------------------------|------------|------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `id`                                  | `INTEGER` | NOT NULL<br/>PRIMARY KEY<br/>AUTOINCREMENT |            | The tournament ID                                                                                                                                          |
| `uniq_id`                             | `TEXT`    | NOT NULL                                   |            | The unique text ID of the tournament                                                                                                                       |
| `name`                                | `TEXT`    | NOT NULL                                   |            | The tournament name                                                                                                                                        |
| `path`                                | `TEXT`    |                                            |            | The absolute or relative path where the tournament file is stored                                                                                          |
| `filename`                            | `TEXT`    |                                            |            | The name of the tournament's Papi file, without the `.papi` extension                                                                                      |
| `time_control_initial_time`           | `INTEGER` |                                            |            | The initial time on the clock in seconds (can be zero if incremented)                                                                                      |
| `time_control_increment`              | `INTEGER` |                                            |            | The time increment gained by the players on each shot                                                                                                      |
| `time_control_handicap_penalty_step`  | `INTEGER` |                                            |            | The time subtracted from the higher-ranked player, in seconds (this time is multiplied by the number of increments of difference between the two players)  |
| `time_control_handicap_penalty_value` | `INTEGER` |                                            |            | The number of points of difference between the players' rankings used to calculate the number of penalties applied to the higher-ranked player             |
| `time_control_handicap_min_time`      | `INTEGER` |                                            |            | The minimum time that will be granted to the highest-ranked player, even if the difference in ranking is very significant                                  |
| `record_illegal_moves`                | `INTEGER` |                                            |            | The maximum number of illegal moves that can be recorded for a player per round If this number is not specified, the event's default configuration is used |
| `rules`                               | `TEXT`    |                                            |            | The URL or server path to the tournament rules, in PDF format (by default, the event rules)                                                                |
| `check_in_open`                       | `INTEGER` |                                            |            | Boolean:<br/>- `1`: Checking is open;<br/>- `0`: Checking is closed                                                                                        |
| `last_update`                         | `FLOAT`   | NOT NULL                                   |            | The last date the tournament was modified                                                                                                                  |
| `last_illegal_move_update`            | `FLOAT`   | NOT NULL<br/>DEFAULT 0.0                   |            | The last date illegal moves in the tournament were modified                                                                                                |
| `last_result_update`                  | `FLOAT`   | NOT NULL<br/>DEFAULT 0.0                   |            | The last date a tournament result was modified                                                                                                             |
| `last_check_in_update`                | `FLOAT`   | NOT NULL<br/>DEFAULT 0.0                   |            | The last date the tournament score was modified                                                                                                            |
| `first_board_number`                  | `INTEGER` |                                            |            | The first board number                                                                                                                                     |
| `paired_bye_result`                   | `INTEGER` |                                            |            | Result awarded to bye players                                                                                                                              |
| `max_byes`                            | `INTEGER` |                                            |            | The maximum number of byes a player can claim                                                                                                              |
| `last_rounds_no_byes`                 | `INTEGER` |                                            |            | The number of final rounds for which players cannot take byes                                                                                              |
| `tie_breaks`                          | `TEXT`    |                                            |            | The tie-breaks used in JSON format (list of dictionaries in the format {'type': str, 'options': dict[str,any]})                                            |
| `rounds`                              | `INTEGER` | NOT NULL<br/>DEFAULT 1                     |            | The tournament's round count                                                                                                                               |
| `rating`                              | `INTEGER` | NOT NULL<br/>DEFAULT 1                     |            | The tournament's rating:<br/>- `1`: Estimated<br/>- `2`: National<br/>- `3`: Fide                                                                          |
| `pairing`                             | `TEXT`    |                                            |            | The tournament's pairing as a string                                                                                                                       |
| `pairing_settings`                    | `TEXT`    |                                            |            | The tournament's pairing settings, in JSON format                                                                                                          |
| `current_round`                       | `INTEGER` |                                            |            | The tournament's current round                                                                                                                             |
| `chessevent_user_id`                  | `TEXT`    |                                            | chessevent | The username used to log in to the _ChessEvent_ platform                                                                                                   |
| `chessevent_password`                 | `TEXT`    |                                            | chessevent | The password used to log in to the _ChessEvent_ platform                                                                                                   |
| `chessevent_event_id`                 | `TEXT`    |                                            | chessevent | The _ChessEvent_ event ID on the platform                                                                                                                  |
| `chessevent_tournament_name`          | `TEXT`    |                                            | chessevent | The tournament ID on the _ChessEvent_ platform                                                                                                             |
| `chessevent_last_download_md5`        | `TEXT`    |                                            | chessevent | The hash of the tournament's last download from the _ChessEvent_ platform                                                                                  |
| `ffe_id`                              | `INTEGER` |                                            | ffe        | The tournament's approval number on the FFE federal website                                                                                                |
| `ffe_password`                        | `TEXT`    |                                            | ffe        | The tournament access code on the FFE federal website (consisting of 10 capital letters)                                                                   |
| `ffe_last_upload`                     | `FLOAT`   | NOT NULL<br/>DEFAULT 0.0                   | ffe        | The date the tournament was last uploaded to the FFE federal website                                                                                       |
| `ffe_last_rules_upload`               | `FLOAT`   | NOT NULL<br/>DEFAULT 0.0                   | ffe        | The date of the last sending of the tournament rules to the FFE federal website                                                                            |

### `illegal_move` (illegal moves)

| Field           | Type      | Constraint                                 | Ext | Description                                     |
|-----------------|-----------|--------------------------------------------|-----|-------------------------------------------------|
| `id`            | `INTEGER` | NOT NULL<br/>PRIMARY KEY<br/>AUTOINCREMENT |     | The ID of the illegal move                      |
| `tournament_id` | `INTEGER` | NOT NULL<br/>REFERENCES `tournament`(`id`) |     | The tournament ID                               |
| `round`         | `INTEGER` | NOT NULL                                   |     | The round number                                |
| `player_id`     | `INTEGER` | NOT NULL                                   |     | The player ID (in the tournament's _Papi_ file) |
| `date`          | `FLOAT`   | NOT NULL                                   |     | The recording date                              |

### `result` (results)

| Field             | Type      | Constraint                                 | Ext | Description                                                                                                                                                         |
|-------------------|-----------|--------------------------------------------|-----|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `id`              | `INTEGER` | NOT NULL<br/>PRIMARY KEY<br/>AUTOINCREMENT |     | The result ID                                                                                                                                                       |
| `tournament_id`   | `INTEGER` | NOT NULL<br/>REFERENCES `tournament`(`id`) |     | The tournament ID                                                                                                                                                   |
| `round`           | `INTEGER` | NOT NULL                                   |     | The round number                                                                                                                                                    |
| `board_id`        | `INTEGER` | NOT NULL                                   |     | The board number                                                                                                                                                    |
| `white_player_id` | `INTEGER` | NOT NULL                                   |     | The number of the White player (in the tournament _Papi_ file)                                                                                                      |
| `black_player_id` | `INTEGER` | NOT NULL                                   |     | The number of the player with Black (in the tournament's _Papi_ file)                                                                                               |
| `date`            | `FLOAT`   | NOT NULL                                   |     | The registration date                                                                                                                                               |
| `value`           | `INTEGER` | NOT NULL                                   |     | The result:<br/>- `1`: Black wins<br/>- `2`: draw<br/>- `3`: White wins<br/>- `4`: Black wins by forfeit<br/>- `5`: double forfeit<br/>- `6`: White wins by forfeit |

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
