# _Sharly Chess_ - Interfacing with _ChessEvent_

_Sharly Chess_ can retrieve registrations made on the _ChessEvent_ platform by activating the _ChessEvent_ plugin:

- [The _ChessEvent_ plugin](https://sharly-chess.com/chessevent-plugin) (user documentation)

This page describes the technical aspects of _Sharly Chess_'s interfacing with the _ChessEvent_ platform.

## Authentication

Downloading requires authentication to limit the dissemination of player contact information (email addresses and phone numbers).

The credentials used for authentication are those of the _ChessEvent_ platform (administrator, user, or event manager).

## Download Requests

### URL

The request URL is https://services.breizh-chess-online.fr/chessevent/download.

### Parameters

All parameters are passed in clear text in the payload of the HTTPS request (POST method).

| Parameter          | Description                                       | Example                |
|--------------------|---------------------------------------------------|------------------------|
| `user_id`          | The user's FFE ID on the _ChessEvent_ platform.   | `C69548`               |
| `password`         | The user's password on the _ChessEvent_ platform. | `my-password`          |
| `event_id`         | The event ID on the _ChessEvent_ platform.        | `BRE_35_domloupfide36` |
| `tournament_name`  | The tournament name on the _ChessEvent_ platform. | `Tournoi A`            |

## Expected Data

### Tournament Description

The data received is expected as a dictionary in JSON format (`Content-Type: application/json`).

| Field                                       | Type        | Description                                                                                                                                                                                                                                                                 |
|---------------------------------------------|-------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `name`                                      | `str`       | The name.                                                                                                                                                                                                                                                                   |
| `type`                                      | `enum`      | The type:<br/>`1` = Swiss<br/>`2` = All Rounds                                                                                                                                                                                                                              |
| `rounds`                                    | `int`       | The number of rounds.                                                                                                                                                                                                                                                       |
| `pairing`                                   | `enum`      | The pairing:<br/>`1` = Standard<br/>`2` = Haley<br/>`3` = Soft Haley<br/>`4` = SAD<br/>`5` = Nice Accelerated<br/>`6` = Berger<br/>                                                                                                                                         |
| `time_control`                              | `str`       | The time control.                                                                                                                                                                                                                                                           |
| `location`                                  | `str`       | The location.                                                                                                                                                                                                                                                               |
| `arbiter`                                   | `str`       | The arbiter.                                                                                                                                                                                                                                                                |
| `start`                                     | `timestamp` | The start date.                                                                                                                                                                                                                                                             |
| `end`                                       | `timestamp` | The end date.                                                                                                                                                                                                                                                               |
| `tie_break_1`, `tie_break_2`, `tie_break_3` | `enum`      | Tiebreakers:<br/>`0` = _no tiebreaker_<br/>`1` = Buchholz<br/>`2` = Truncated Buchholz<br/>`3` = Median Buchholz<br/>`4` = Cumulative<br/>`5` = Performance<br/>`6` = Sum of Buchholz<br/>`7` = Number of wins<br/>`8` = Kashdan<br/>`9` = Koya<br/>`10` = Sonneborn-Berger |
| `rating`                                    | `enum`      | The rankings used:<br/>`1` = Standard<br/>`2` = Rapid<br/>`3` = Blitz                                                                                                                                                                                                       |
| `players`                                   | `list`      | The list of players (details below).                                                                                                                                                                                                                                        |

Example of tournament:

`{`<br/>
&nbsp;&nbsp;`'name': '36e open Fide de Domloup',`<br/>
&nbsp;&nbsp;`'type': 1,` # Swiss<br/>
&nbsp;&nbsp;`'rounds': 5,`<br/>
&nbsp;&nbsp;`'pairing': 1,` # Standard<br/>
&nbsp;&nbsp;`'time_control': 'G3600 + 30',`<br/>
&nbsp;&nbsp;`'location': 'Domloup',`<br/>
&nbsp;&nbsp;`'arbiter': 'AUBRY Pascal C69548',`<br/>
&nbsp;&nbsp;`'start': 1708767000,` # 2024-02-24 09:30<br/>
&nbsp;&nbsp;`'end': 1708880400,` # 2024-02-25 17:00<br/>
&nbsp;&nbsp;`'tie_break_1': 2,` # Buchholz truncated<br/>
&nbsp;&nbsp;`'tie_break_2': 3,` # Buchholz median<br/>
&nbsp;&nbsp;`'tie_break_3': 5,` # Performance<br/>
&nbsp;&nbsp;`'rating': 1,` # Standard<br/>
&nbsp;&nbsp;`'players': [`<br/>
&nbsp;&nbsp;&nbsp;&nbsp;`...`<br/>
&nbsp;&nbsp;`],`<br/>
`}`

### Player description

| Field                  | Type        | Description                                                                                                                                                                                                          |
|------------------------|-------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `last_name`            | `str`       | The last name.                                                                                                                                                                                                       |
| `first_name`           | `str`       | The first name.                                                                                                                                                                                                      |
| `gender`               | `enum`      | The gender:<br/>`0` = _none_<br/>`1` = Female<br/>`2` = Male                                                                                                                                                         |
| `birth`                | `timestamp` | The date of birth.                                                                                                                                                                                                   |
| `federation`           | `str`       | The federation code (FED).                                                                                                                                                                                           |
| `fide_id`              | `int`       | The Fide identifier.                                                                                                                                                                                                 |
| `ffe_id`               | `str`       | The FFE identifier (RefFFE field in Papi).                                                                                                                                                                           |
| `ffe_licence`          | `enum`      | Licence:<br/>`0` = _none_<br/>`1` = Licence not renewed (N)<br/>`2` = Licence B<br/>`3` = Licence A                                                                                                                  |
| `ffe_licence_number`   | `str`       | The FFE licence number (`NrFFE` field in _Papi_, in `XNNNNN` format).                                                                                                                                                |
| `ffe_league`           | `str`       | The league code (LIG).                                                                                                                                                                                               |
| `ffe_club_id`          | `int`       | The club ID number.                                                                                                                                                                                                  |
| `ffe_club`             | `str`       | The club.                                                                                                                                                                                                            |
| `category`             | `enum`      | The category:<br/>`0` = _none_<br/>`1` = U8 (Ppo)<br/>`2` = U10 (Pou)<br/>`3` = U12 (Pup)<br/>`4` = U14 (Ben)<br/>`5` = U16 (Min)<br/>`6` = U18 (Cad)<br/>`7` = U20 (Jun)<br/>`8` = Sen<br/>`9` = Sep<br/>`10` = Vet |
| `standard_rating`      | `int`       | The standard rating.                                                                                                                                                                                                 |
| `standard_rating_type` | `enum`      | The standard rating type:<br/>`1` = Estimated<br/>`2` = National<br/>`3` = FIDE                                                                                                                                      |
| `rapid_rating`         | `int`       | The rapid rating.                                                                                                                                                                                                    |
| `rapid_rating_type`    | `enum`      | The rapid rating type (see `standard_rating_type`).                                                                                                                                                                  |
| `blitz_rating`         | `int`       | The blitz rating.                                                                                                                                                                                                    |
| `blitz_rating_type`    | `enum`      | The blitz rating type (see `standard_rating_type`).                                                                                                                                                                  |
| `title`                | `enum`      | The title:<br/>`0` = _none_<br/>`1` = Woman's FIDE Master<br/>`2` = FIDE Master<br/>`3` = Woman International Master<br/>`4` = International Master<br/>`5` = Woman Grandmaster<br/>`6` = Grandmaster                |
| `email`                | `str`       | The email address.                                                                                                                                                                                                   |
| `phone`                | `str`       | The phone number.                                                                                                                                                                                                    |
| `fee`                  | `float`     | The registration fee.                                                                                                                                                                                                |
| `paid`                 | `float`     | The amount paid.                                                                                                                                                                                                     |
| `check_in`             | `bool`      | `true` if the player checked in, `false` otherwise.                                                                                                                                                                  |
| `board`                | `int`       | A fixed board number, `0` otherwise.                                                                                                                                                                                 |
| `skipped_rounds`       | `dict`      | A dictionary with unplayed rounds as the key and the points scored as the value: `0.0` = Zero-Point Bye, `0.5` = Half-Point Bye, `1.0` = Full-Point Bye.                                                             |

Example of player:

`{`<br/>
&nbsp;&nbsp;`'last_name': 'AUBRY',`<br/>
&nbsp;&nbsp;`'first_name': 'Pascal',`<br/>
&nbsp;&nbsp;`'ffe_id': 'C69548',`<br/>
&nbsp;&nbsp;`'fide_id': 20671806,`<br/>
&nbsp;&nbsp;`'gender': 2,`<br/>
&nbsp;&nbsp;`'birth': -41990400,` # 1968-09-02<br/>
&nbsp;&nbsp;`'category': 9,` # Sep<br/>
&nbsp;&nbsp;`'standard_rating': 1664,`<br/>
&nbsp;&nbsp;`'standard_rating_type': 3,` # F<br/>
&nbsp;&nbsp;`'rapid_rating': 1664,`<br/>
&nbsp;&nbsp;`'rapid_rating_type': 3,` # F<br/>
&nbsp;&nbsp;`'blitz_rating': 1664,`<br/>
&nbsp;&nbsp;`'blitz_rating_type': 1,` # E<br/>
&nbsp;&nbsp;`'title': 0,`<br/>
&nbsp;&nbsp;`'license': 3, # A`<br/>
&nbsp;&nbsp;`'federation': 'FRA',`<br/>
&nbsp;&nbsp;`'league': 'BRE',`<br/>
&nbsp;&nbsp;`'club_id': 1918,`<br/>
&nbsp;&nbsp;`'club': 'Echiquier Domloupéen',`<br/>
&nbsp;&nbsp;`'email': 'pascal.aubry@echecs35.fr',`<br/>
&nbsp;&nbsp;`'phone': '0677939521',`<br/>
&nbsp;&nbsp;`'fee': 25.0,`<br/>
&nbsp;&nbsp;`'paid': 25.0,`<br/>
&nbsp;&nbsp;`'check_in': true,`<br/>
&nbsp;&nbsp;`'board': 0,`<br/>
&nbsp;&nbsp;`'skipped_rounds': {`<br/>
&nbsp;&nbsp;&nbsp;&nbsp;`1: 0.5,` # Half-Point Bye at round #1<br/>
&nbsp;&nbsp;&nbsp;&nbsp;`2: 0.0,` # Zero-Point Bye at round #3<br/>
&nbsp;&nbsp;`}`<br/>
`}`

## Error Codes

In case of error, the JSON response contains only one `error: str` field that specifies the error encountered.

The following error codes are used:

| HTTP Status  | Meaning                                                                  | `error` Field          |
|--------------|--------------------------------------------------------------------------|------------------------|
| 200          | _success_                                                                |                        |
| 401          | Authentication problem (unable to log in to the _ChessEvent_ platform)   | `Unauthorized`         |
| 403          | Authorization problem (unauthorized credentials for the requested event) | `Access forbidden`     |
| 497          | User not found                                                           | `User not found`       |
| 498          | Tournament not found                                                     | `Tournament not found` |
| 499          | Event not found                                                          | `Event not found`      |
| 500          | Other errors                                                             | Specify                |
