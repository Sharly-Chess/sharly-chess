# _Sharly Chess_ - Authentication and roles

This page is a proposal to add roles in the application, not implemented yet.

## Roles in version 2.4

In version 2.4, _Sharly Chess_ distinguishes two roles:
- **the arbiter role** (which is obtained by connecting from the server `127.0.0.1`), which can access:
  - the administration pages, or arbiter pages;
  - the public pages, with some additional privileges.
- **the standard role**, which allows:
  - to view public screens;
  - to score and enter results (with or without password protection).

## Development Proposal

### Roles

The roles in _Sharly Chess_ are:

- **Administrator** (of the application)
- **Organizer** (of an event)
- **Display manager** (of an event)
- **Chief Arbiter** (of an event)
- **Deputy Chief Arbiter** (of an event)
- **Pairings Officer** (of tournaments)
- **Sector Arbiter** (of tournaments)
- **Result Officer** (of tournaments)
- **Check-in officer** (of tournaments)
- **Spectator** (of an event)

The arbiter roles are directly inspired by the FIDE hierarchical system:
- The **Chief Arbiter** with admin-like rights over the event;
- The **Deputy Chief Arbiter(s)** with lower rights over basically the whole event;
- The **Sector Arbiter(s)** with rights over their sector (a sector being a set of tournaments);
- The **Pairings Officer(s)** with full pairings management rights over a set of tournaments;
- The Match Arbiter(s) - who can set results for their sector - are named **Results Officer** since this role may be assigned to players in _Sharly Chess_.

Some roles 'include' other roles:
- Administrators can do anything all the other roles can do;
- Organizers can do anything Display Managers can do;
- Chief Arbiters can do anything Deputy Chief Arbiters can do;
- Deputy Chief Arbiters can do anything Sector Arbiters and Pairing Officers can do;
- Sector Arbiters can do anything Results Officers and Check-in Officers can do.
- All the roles can do anything Spectators can do.

> [!NOTE]
> - In Continental and World events, the CA, DCA and SA roles are mostly management positions (although they can intervene on games if Match Arbiters can't do it, of course), so they wouldn't play with the software once the rights are set up.
> - Pairings Officer are the ones doing the bulk of the work on the pairings software (especially in case of team tournaments)
> - Match Arbiters are focused on the games, so can enter results, but that's about it (although they should be able to correct wrong results).

### Permissions by role

|                                  |  Administrator  | Organizer | Display<br/>manager | Chief<br/>Arbiter | Deputy<br/>Chief<br/>Arbiter | Pairings<br/>Officer | Sector<br/>Arbiter | Check-in<br/>Officer | Results<br/>Officer | Spectator |        -        |
|----------------------------------|:---------------:|:---------:|:-------------------:|:-----------------:|:----------------------------:|:--------------------:|:------------------:|:--------------------:|:-------------------:|:---------:|:---------------:|
| **Scope**                        | **Application** | **Event** |      **Event**      |     **Event**     |          **Event**           |    **Tournament**    |   **Tournament**   |    **Tournament**    |   **Tournament**    | **Event** | **Application** |
| **APPLICATION MANAGEMENT**       |                 |           |                     |                   |                              |                      |                    |                      |                     |           |                 |
| View application settings        |      :ok:       |    :x:    |         :x:         |        :x:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Update application settings      |      :ok:       |    :x:    |         :x:         |        :x:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Manage administrators            |      :ok:       |    :x:    |         :x:         |        :x:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Add events                       |      :ok:       |    :x:    |         :x:         |        :x:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Source databases management      |      :ok:       |    :x:    |         :x:         |        :x:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| View private events              |      :ok:       |    :x:    |         :x:         |        :x:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| View public events               |      :ok:       |    :x:    |         :x:         |        :x:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |     :ok:(*)     |
| View detailed event cards        |      :ok:       |    :x:    |         :x:         |        :x:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| **EVENTS MANAGEMENT**            |                 |           |                     |                   |                              |                      |                    |                      |                     |           |                 |
| Delete an event                  |      :ok:       |    :x:    |         :x:         |        :x:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Rename an event                  |      :ok:       |    :x:    |         :x:         |        :x:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Manage Accounts                  |      :ok:       |   :ok:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Manage Organizers                |      :ok:       |    :x:    |         :x:         |        :x:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Manage Display Managers          |      :ok:       |   :ok:    |         :x:         |        :x:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Manage Chief Arbiters            |      :ok:       |   :ok:    |         :x:         |        :x:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Manage Deputy Chief Arbiters     |      :ok:       |    :x:    |         :x:         |       :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Manage Sector Arbiters           |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Manage Pairings Officers         |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Manage Results Officers          |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Manage Check-in Officers         |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Manage Spectators                |      :ok:       |   :ok:    |        :ok:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Update an event                  |      :ok:       |   :ok:    |         :x:         |       :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| View the complete event config   |      :ok:       |   :ok:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| View the basic event config      |      :ok:       |   :ok:    |        :ok:         |       :ok:        |             :ok:             |         :ok:         |        :ok:        |         :ok:         |        :ok:         |    :x:    |       :x:       |
| **TOURNAMENTS MANAGEMENT**       |                 |           |                     |                   |                              |                      |                    |                      |                     |           |                 |
| View Tournaments tab             |      :ok:       |   :ok:    |        :ok:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Add tournaments                  |      :ok:       |    :x:    |         :x:         |       :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Delete a tournament              |      :ok:       |    :x:    |         :x:         |       :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Update tournaments               |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Publish results                  |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Publish rules                    |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Download fees                    |      :ok:       |   :ok:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| **PAIRINGS MANAGEMENT**          |                 |           |                     |                   |                              |                      |                    |                      |                     |           |                 |
| Use the pairing engine           |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :ok:         |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Manually pair players            |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :ok:         |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| View draft pairings              |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :ok:         |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Publish pairings                 |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| View draft rankings              |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Publish rankings                 |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| **CHECK-IN MANAGEMENT**          |                 |           |                     |                   |                              |                      |                    |                      |                     |           |                 |
| Open/close check-in              |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| **DISPLAY MANAGEMENT**           |                 |           |                     |                   |                              |                      |                    |                      |                     |           |                 |
| Manage screens/families/rotators |      :ok:       |   :ok:    |        :ok:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Manage timers                    |      :ok:       |   :ok:    |        :ok:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| **PLAYERS MANAGEMENT**           |                 |           |                     |                   |                              |                      |                    |                      |                     |           |                 |
| Add players                      |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Delete players                   |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Update players                   |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Check-in players                 |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :ok:        |         :ok:         |         :x:         |    :x:    |       :x:       |
| **RESULTS MANAGEMENT**           |                 |           |                     |                   |                              |                      |                    |                      |                     |           |                 |
| Enter results                    |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :ok:        |         :x:          |        :ok:         |    :x:    |       :x:       |
| Modify results                   |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| Use special results              |      :ok:       |    :x:    |         :x:         |       :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |         :x:         |    :x:    |       :x:       |
| **VIEWING**                      |                 |           |                     |                   |                              |                      |                    |                      |                     |           |                 |
| View private displays            |      :ok:       |   :ok:    |        :ok:         |       :ok:        |             :ok:             |         :ok:         |        :ok:        |         :ok:         |        :ok:         |    :x:    |       :x:       |
| View public displays             |      :ok:       |   :ok:    |        :ok:         |       :ok:        |             :ok:             |         :ok:         |        :ok:        |         :ok:         |        :ok:         |   :ok:    |       :x:       |

(*) Accessing the list of the public events is needed to authenticate (the accounts are defined at event-level).

### Computers

Computers are defined on the web UI by:
- an IP address (the IP address of the machine accessing the _Sharly Chess_ server);
- several comma-separated IP addresses.

#### Examples

| :unlock:/:lock: |     Computer      | Comment           |
|:---------------:|:-----------------:|:------------------|
|     :lock:      |         -         | Any computer      |
|     :lock:      |   ``127.0.0.1``   | The server itself |
|                 | ``192.168.1.115`` | A local computer  |

#### Computer roles

Computers can be given roles, without any other authentication.

> [!NOTE]
> They must be trusted computers on a trusted network!

| :unlock:/:lock: |     Computer      |        Comment         |   Administrator    | Organizer | Display<br/>Manager | Chief<br/>arbiter | Deputy<br/>Chief<br/>arbiter | Pairings<br/>Officer | Sector<br/>Arbiter | Check-in<br/>Officer | Result<br/>Officer |     Spectator      |
|:---------------:|:-----------------:|:----------------------:|:------------------:|:---------:|:-------------------:|:-----------------:|:----------------------------:|:--------------------:|:------------------:|:--------------------:|:------------------:|:------------------:|
|     :lock:      |   ``127.0.0.1``   | Server (Chief Arbiter) | :white_check_mark: |   :ok:    |        :ok:         |       :ok:        |             :ok:             |         :ok:         |        :ok:        |         :ok:         |        :ok:        |        :ok:        |
|                 | ``192.168.1.100`` |  Deputy Chief Arbiter  |        :x:         |    :x:    |         :x:         |        :x:        |      :white_check_mark:      |         :ok:         |        :ok:        |         :ok:         |        :ok:        |        :ok:        |
|                 | ``192.168.1.115`` |   Check-in computer    |        :x:         |    :x:    |         :x:         |        :x:        |             :x:              |         :x:          |        :x:         |  :white_check_mark:  |        :x:         |        :ok:        |
|                 | ``192.168.1.119`` |    Result computer     |        :x:         |    :x:    |                     |        :x:        |             :x:              |         :x:          |        :x:         |         :x:          | :white_check_mark: |        :ok:        |
|                 |         -         |    Display computer    |        :x:         |    :x:    |                     |        :x:        |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         | :white_check_mark: |

> [!NOTE]
> Connections from the server automatically have the Administrator role (not configurable).

### Users

Users are defined on the web UI by credentials:
- a unique username;
- a password.

#### Examples

| :unlock:/:lock: |     User      | Comment                       |
|:---------------:|:-------------:|:------------------------------|
|                 |  ``arbiter``  | The chief arbiter |
|                 | ``127.0.0.1`` | The server itself             |
|                 |       -       | Anauthenticated               |

> [!NOTE]
> No need to authenticate on the server, the Administrator role is automatically given to the server.

#### User roles

Users can be given roles, after they authenticate.

| :unlock:/:lock: |       User        |           Comment           |   Administrator    | Organizer | Display<br/>Manager | Chief<br/>arbiter | Deputy<br/>Chief<br/>arbiter | Pairings<br/>Officer | Sector<br/>Arbiter | Check-in<br/>Officer | Result<br/>Officer  |     Spectator      |
|:---------------:|:-----------------:|:---------------------------:|:------------------:|:---------:|:-------------------:|:-----------------:|:----------------------------:|:--------------------:|:------------------:|:--------------------:|:-------------------:|:------------------:|
|                 |     ``mary``      |    Deputy Chief Arbiter     |        :x:         |    :x:    |         :x:         |        :x:        |      :white_check_mark:      |         :ok:         |        :ok:        |         :ok:         |        :ok:         |        :ok:        |
|                 |     ``john``      | Check-in and Result Officer |        :x:         |    :x:    |         :x:         |        :x:        |             :x:              |         :x:          |        :x:         |  :white_check_mark:  | :white_check_mark:  |        :ok:        |
|                 |         -         |      _Unauthenticated_      |        :x:         |    :x:    |                     |        :x:        |             :x:              |         :x:          |        :x:         |         :x:          |         :x:         | :white_check_mark: |
