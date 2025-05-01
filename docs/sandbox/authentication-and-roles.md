# _Sharly Chess_ - Authentication and roles

This page is a proposal to add roles in the application, not implemented yet.

## Roles in version 2.4

In version 2.4, _Sharly Chess_ distinguishes two roles:
- **the arbiter role**, which is obtained by connecting from the server `127.0.0.1`), which can access:
  - the administration pages, or arbiter pages;
  - the public pages, with some additional privileges.
- **the standard role**, which allows:
  - to view public screens;
  - to score and enter results (with or without password protection).

## Development Proposal

### Roles

- **Administrator** (of the application)
- **Organizer** (of an event)
- **Chief Arbiter** (of an event or tournament)
- **Arbiter** (of an event or tournament)
- **Check-in officer** (of an event)
- **Result officer** (of an event)
- **Spectator** (of an event)

### Actions autorisées par rôle

|                                  |  Administrator  | Organizer | Chief arbiter  |    Arbiter     | Check-in officer | Result officer | Spectator |
|----------------------------------|:---------------:|:---------:|:--------------:|:--------------:|:----------------:|:--------------:|:---------:|
| **Scope**                        | **Application** | **Event** | **Tournament** | **Tournament** |    **Event**     |   **Event**    | **Event** |
| **APPLICATION MANAGEMENT**       |                 |           |                |                |                  |                |           |
| Update application settings      |      :ok:       |    :x:    |      :x:       |      :x:       |       :x:        |      :x:       |    :x:    |
| Manage dministrators             |      :ok:       |    :x:    |      :x:       |      :x:       |       :x:        |      :x:       |    :x:    |
| **EVENT MANAGEMENT**             |                 |           |                |                |                  |                |           |
| Add an Event                     |      :ok:       |    :x:    |      :x:       |      :x:       |       :x:        |      :x:       |    :x:    |
| Delete an event                  |      :ok:       |    :x:    |      :x:       |      :x:       |       :x:        |      :x:       |    :x:    |
| Rename an event                  |      :ok:       |    :x:    |      :x:       |      :x:       |       :x:        |      :x:       |    :x:    |
| Edit an event                    |      :ok:       |   :ok:    |      :x:       |      :x:       |       :x:        |      :x:       |    :x:    | :x: |
| **TOURNAMENT MANAGEMENT**        |                 |           |                |                |                  |                |           |
| Add tournaments                  |       :x:       |    :x:    |      :ok:      |      :x:       |       :x:        |      :x:       |    :x:    |
| Delete a tournament              |       :x:       |    :x:    |      :ok:      |      :x:       |       :x:        |      :x:       |    :x:    |
| Edit tournaments                 |       :x:       |    :x:    |      :ok:      |      :x:       |       :x:        |      :x:       |    :x:    |
| Open/close check-in              |       :x:       |    :x:    |      :ok:      |      :x:       |       :x:        |      :x:       |    :x:    |
| Use the pairing engine           |       :x:       |    :x:    |      :ok:      |      :x:       |       :x:        |      :x:       |    :x:    |
| Manually pair players            |       :x:       |    :x:    |      :ok:      |      :x:       |       :x:        |      :x:       |    :x:    |
| Publish pairings                 |       :x:       |    :x:    |      :ok:      |      :x:       |       :x:        |      :x:       |    :x:    |
| View pairings before publication |       :x:       |    :x:    |      :ok:      |      :ok:      |       :x:        |      :x:       |    :x:    |
| Calculate rankings               |       :x:       |    :x:    |      :ok:      |      :x:       |       :x:        |      :x:       |    :x:    |
| Publish rankings                 |       :x:       |    :x:    |      :ok:      |      :x:       |       :x:        |      :x:       |    :x:    |
| View rankings before publication |       :x:       |    :x:    |      :ok:      |      :ok:      |       :x:        |      :x:       |    :x:    |
| Publish rankings online          |       :x:       |    :x:    |      :ok:      |      :x:       |       :x:        |      :x:       |    :x:    |
| **DISPLAY MANAGEMENT**           |                 |           |                |                |                  |                |           |
| Manage screens/families/rotators |       :x:       |   :ok:    |      :ok:      |      :x:       |       :x:        |      :x:       |    :x:    |
| Manage timers                    |       :x:       |   :ok:    |      :ok:      |      :x:       |       :x:        |      :x:       |
| **PLAYERS MANAGEMENT**           |                 |           |                |                |                  |                |           |
| Add players                      |       :x:       |    :x:    |      :ok:      |      :x:       |       :x:        |      :x:       |    :x:    |
| Delete players                   |       :x:       |    :x:    |      :ok:      |      :x:       |       :x:        |      :x:       |    :x:    |
| Edit players                     |       :x:       |    :x:    |      :ok:      |      :x:       |       :x:        |      :x:       |    :x:    |
| Check-in players                 |       :x:       |    :x:    |      :ok:      |      :ok:      |       :ok:       |      :x:       |    :x:    |
| **RESULTS MANAGEMENT**           |                 |           |                |                |                  |                |           |
| Use special results              |       :x:       |    :x:    |      :ok:      |      :x:       |       :x:        |      :x:       |    :x:    |
| Modify results                   |       :x:       |    :x:    |      :ok:      |      :ok:      |       :x:        |      :x:       |    :x:    |
| Enter results                    |       :x:       |    :x:    |      :ok:      |      :ok:      |       :x:        |      :ok:      |    :x:    |
| **VIEWING**                      |                 |           |                |                |                  |                |           |
| View check-in                    |      :ok:       |   :ok:    |      :ok:      |      :ok:      |       :ok:       |      :ok:      |   :ok:    |
| View pairings                    |      :ok:       |   :ok:    |      :ok:      |      :ok:      |       :ok:       |      :ok:      |
| View results                     |      :ok:       |   :ok:    |      :ok:      |      :ok:      |       :ok:       |      :ok:      |   :ok:    |

### Role Assignment

Roles are assigned:
- by client (the IP address of the machine accessing the _Sharly Chess_ server);
- by authentication (a username and password);
- by client and by authentication.

### Example of role assignment

In the example below:
- Connections from the server automatically have all roles (not configurable);
- Connections from the client ``192.168.1.115`` and authenticated with the username ``big-boss`` have the organization and chief referee roles for all tournaments;
- Connections authenticated with the usernames ``boss-1`` and ``boss-2`` have the referee role, for tournaments A/B and C/D respectively;
- The last two workstations allow check-in and results entry, respectively;
- Other unauthenticated clients can view the display screens.

|      Client       |      ID      |      Comment      | Tournament | Administrator | Organizer | Chief arbiter | Arbiter | Check-in<br/>officer | Result<br/>officer | Spectator |
|:-----------------:|:------------:|:-----------------:|:----------:|:-------------:|:---------:|:-------------:|:-------:|:---------------------:|:--------------:|:---------:|
|   ``127.0.0.1``   |      -       |      Server       |     -      |     :ok:      |   :ok:    |     :ok:      |  :ok:   |         :ok:          |      :ok:      |   :ok:    |
| ``192.168.1.115`` | ``big-boss`` |   Chief arbiter   |            |      :x:      |   :ok:    |     :ok:      |  :ok:   |         :ok:          |      :ok:      |   :ok:    |
|         -         |  ``boss-1``  |      Arbiter      |    A, B    |      :x:      |    :x:    |      :x:      |  :ok:   |         :ok:          |      :ok:      |   :ok:    |
|         -         |  ``boss-2``  |      Arbiter      |    C, D    |      :x:      |    :x:    |      :x:      |  :ok:   |         :ok:          |      :ok:      |   :ok:    |
| ``192.168.1.27``  |      -       | Check-in computer |            |      :x:      |    :x:    |      :x:      |   :x:   |         :ok:          |      :x:       |   :ok:    |
| ``192.168.1.226`` |      -       |  Result computer  |            |      :x:      |    :x:    |      :x:      |   :x:   |          :x:          |      :ok:      |   :ok:    |
|         -         |      -       |                   |            |      :x:      |    :x:    |      :x:      |   :x:   |          :x:          |      :x:       |   :ok:    |
