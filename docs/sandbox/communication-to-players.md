# _Sharly Chess_ - Communicating with players

This page is dedicated to communication with players, for quick implementation in _Sharly Chess_.

## Target media

The following two target media are considered:

- Email;
- SMS or MMS.

In both cases, the information used for communication is that provided by players upon registration (for example the information entered on _ChessEvent_ is retrieved by _Sharly Chess_).

## Mailing Recipients

The system must be as flexible as possible and allow mailings to:

- all players in an event
- all players in a tournament
- all players paired in the current round of a tournament
- the Paired Allocated Bye player in the current round of a tournament
- one or more players in a tournament chosen by the referee

## Content and customization

Arbiters must be able to rely on standard messages, for example, to:

- warn of the imminent opening or closing of the check-in
- warn of the publication of pairings
- send the rankings

All messages must be customizable using the following tokens.

| Scope                         | *Token*                   | Replacement                                                               |
|-------------------------------|---------------------------|---------------------------------------------------------------------------|
| Event (**ev***ent*)           | `{{ev_name}}`             | The name of the event                                                     |
| Tournament (**to***urnament*) | `{{to_name}}`             | The name of the tournament                                                |
|                               | `{{to_ffe_url}}`          | The URL of the tournament listing on the federal website                  |
| Current Round (**ro***und*)   | `{{ro_number}}`           | The number of the current round                                           |
|                               | `{{ro_datetime}}`         | The date and time of the current round                                    |
|                               | `{{ro_time}}`             | The time of the current round                                             |
| Player (**pl***ayer*)         | `{{pl_last_name}}`        | The player's last name                                                    |
|                               | `{{pl_first_name}}`       | The player's last name                                                    |
|                               | `{{pl_gender}}`           | The player's last name                                                    |
|                               | `{{pl_name}}`             | The player's full name                                                    |
|                               | `{{pl_rating}}`           | The player's rating                                                       |
|                               | `{{pl_rating_type}}`      | The player's rating type (Fide, National, Estimated)                      |
|                               | `{{pl_points}}`           | The player's points                                                       |
|                               | `{{pl_standings_points}}` | The player's actual points                                                |
| Pairing (**pa***iring*)       | `{{pa_paired}}`           | True if the player is paired, False otherwise                             |
|                               | `{{pa_paired_bye}}`       | True if the player is assigned the Pairing Allocated Bye, False otherwise |
|                               | `{{pa_unpaired}}`         | True if the player is unpaired, False otherwise                           |
|                               | `{{pa_unpaired_hp_bye}}`  | True if the player is unpaired with a half-point bye, False otherwise     |
|                               | `{{pa_unpaired_fp_bye}}`  | True if the player is unpaired with a bye, False otherwise                |
|                               | `{{pa_board}}`            | The board number of the pairing                                           |
|                               | `{{pa_color}}`            | The color of the pairing                                                  |
| Opponent (**op***ponent*)     | `{{op_last_name}}`        | The opponent's last name                                                  |
|                               | `{{op_first_name}}`       | The opponent's last name                                                  |
|                               | `{{op_gender}}`           | The opponent's last name                                                  |
|                               | `{{op_name}}`             | The opponent's full name                                                  |
|                               | `{{op_rating}}`           | The opponent's rating                                                     |
|                               | `{{op_rating_type}}`      | The opponent's rating type (Fide, National, Estimé)                       |
|                               | `{{op_points}}`           | The opponent's number of points                                           |
|                               | `{{op_standings_points}}` | The player's actual number of points                                      |

The Jinja template engine is used for content customization, which allows, for example, the use of the alternatives `{% if %}`...`{% else %}`...`{% endif %}`:

```
Hello {{pl_first_name}},
Tournament: {{to_name}}
Pairing for round #{{ro_number}}:
{% if pa_paired %}
{% if pa_paired_bye }}
Pairing Allocated Bye
{% else %}
Opponent: {{op_name}} {{op_rating}}{{op_rating_type}} [{{op_points}}]
Color: {{pa_color}}
Board: {{pa_board}}
{% endif %}
{% endif %}
{% if pa_unpaired %}
  Not paired {% if pa_unpaired_bye_hp %}Half-Point Bye{% endif %}{% if pa_unpaired_bye_fp %}Full-Point Bye{% endif %}
{% endif %}
```

## Sending Engines

Multiple sending engines can be defined on the application, and can be used by all tournaments and all events.

### Email Sending Engine

An email sending engine is defined using the following parameters.

| Parameter            | Type | Meaning                                                                                                                         |
|----------------------|------|---------------------------------------------------------------------------------------------------------------------------------|
| `type`               | enum | Value `smtp`                                                                                                                    |
| `smtp_host`          | str  | The SMTP server (required)                                                                                                      |
| `smtp_security`      | enum | none (`smtp_port` = `25` by default)<br/>STARTTLS (`smtp_port` = `587` by default)<br/>SSL/TLS (`smtp_port` = `465` by default) |
| `smtp_port`          | int  | The port used (optional)                                                                                                        |
| `smtp_user`          | str  | The account used to authenticate to the SMTP server (optional)                                                                  |
| `smtp_password`      | str  | Password (optional)                                                                                                             |
| `smtp_from_mail`     | str  | Sender's email (optional)                                                                                                       |
| `smtp_from_name`     | str  | Sender's name (optional)                                                                                                        |
| `smtp_bcc`           | str  | BCC addresses, separated by commas (optional)                                                                                   |
| `smtp_reply_to_mail` | str  | Reply email (optional)                                                                                                          |
| `smtp_reply_to_name` | str  | Reply name (optional)                                                                                                           |

Sending by email is easy to set up and free; all you need is an email account with a provider.

### _MailJet_ SMS Sending Engine

A _MailJet_ SMS sending engine is defined by the following parameters.

| Parameter           | Type | Meaning                                       |
|---------------------|------|-----------------------------------------------|
| `type`              | enum | Value `sms_mailjet`                           |
| `mailjet_sms_from`  | str  | Sender (optional, defaults to `Sharly Chess`) |
| `mailjet_sms_token` | str  | the authentication token for the MailJet API  |

Sending by SMS is more complex to set up and requires a fee; you must rely on a sending provider (for example, here [_MailJet_](https://mailjet.com)).
