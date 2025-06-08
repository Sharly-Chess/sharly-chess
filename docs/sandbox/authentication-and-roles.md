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
- Chief Arbiters can do anything Deputy Chief Arbiters can do;
- Deputy Chief Arbiters can do anything Sector Arbiters can do;
- Sector Arbiters can do anything Result Officers and Check-in Officers can do.
- All the roles can do anything Spectators can do.

> [!NOTE]
> - In Continental and World events, the CA, DCA and SA roles are mostly management positions (although they can intervene on games if Match Arbiters can't do it, of course), so they wouldn't play with the software once the rights are set up.
> - Pairings Officer are the ones doing the bulk of the work on the pairings software (especially in case of team tournaments)
> - Match Arbiters are focused on the games, so can enter results, but that's about it (although they should be able to correct wrong results).

### Permissions by role

|                                  |  Administrator  | Organizer | Chief<br/>>Arbiter | Deputy<br/>Chief<br/>Arbiter | Pairings<br/>Officer | Sector<br/>Arbiter | Check-in<br/>Officer | Result<br/>Officer | Spectator |
|----------------------------------|:---------------:|:---------:|:------------------:|:----------------------------:|:--------------------:|:------------------:|:--------------------:|:------------------:|:---------:|
| **Scope**                        | **Application** | **Event** |     **Event**      |          **Event**           |    **Tournament**    |   **Tournament**   |    **Tournament**    |   **Tournament**   | **Event** |
| **APPLICATION MANAGEMENT**       |                 |           |                    |                              |                      |                    |                      |                    |           |
| Update application settings      |      :ok:       |    :x:    |        :x:         |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Manage administrators            |      :ok:       |    :x:    |        :x:         |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| **EVENT MANAGEMENT**             |                 |           |                    |                              |                      |                    |                      |                    |           |
| Add an Event                     |      :ok:       |    :x:    |        :x:         |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Delete an event                  |      :ok:       |    :x:    |        :x:         |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Rename an event                  |      :ok:       |    :x:    |        :x:         |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Manage Organizers                |      :ok:       |    :x:    |        :x:         |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Manage Chief Arbiters            |      :ok:       |    :x:    |        :x:         |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Manage Deputy Chief Arbiters     |      :ok:       |    :x:    |        :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Edit an event                    |      :ok:       |   :ok:    |        :x:         |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| **TOURNAMENT MANAGEMENT**        |                 |           |                    |                              |                      |                    |                      |                    |           |
| Add tournaments                  |       :x:       |    :x:    |        :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Delete a tournament              |       :x:       |    :x:    |        :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Edit tournaments                 |       :x:       |    :x:    |        :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Open/close check-in              |       :x:       |    :x:    |        :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Use the pairing engine           |       :x:       |    :x:    |        :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Manually pair players            |       :x:       |    :x:    |        :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Publish pairings                 |       :x:       |    :x:    |        :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| View pairings before publication |       :x:       |    :x:    |        :ok:        |             :ok:             |         :ok:         |        :x:         |         :x:          |        :x:         |    :x:    |
| Calculate rankings               |       :x:       |    :x:    |        :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Publish rankings                 |       :x:       |    :x:    |        :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| View rankings before publication |       :x:       |    :x:    |        :ok:        |             :ok:             |         :ok:         |        :x:         |         :x:          |        :x:         |    :x:    |
| Publish rankings online          |       :x:       |    :x:    |        :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| **DISPLAY MANAGEMENT**           |                 |           |                    |                              |                      |                    |                      |                    |           |
| Manage screens/families/rotators |       :x:       |   :ok:    |        :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Manage timers                    |       :x:       |   :ok:    |        :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| **PLAYERS MANAGEMENT**           |                 |           |                    |                              |                      |                    |                      |                    |           |
| Add players                      |       :x:       |    :x:    |        :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Delete players                   |       :x:       |    :x:    |        :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Edit players                     |       :x:       |    :x:    |        :ok:        |             :ok:             |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| Check-in players                 |       :x:       |    :x:    |        :ok:        |             :ok:             |         :ok:         |        :ok:        |         :ok:         |        :x:         |    :x:    |
| **RESULTS MANAGEMENT**           |                 |           |                    |                              |                      |                    |                      |                    |           |
| Enter results                    |       :x:       |    :x:    |        :ok:        |             :ok:             |         :ok:         |        :ok:        |         :x:          |        :ok:        |    :x:    |
| Modify results                   |       :x:       |    :x:    |        :ok:        |             :ok:             |         :ok:         |        :x:         |         :x:          |        :x:         |    :x:    |
| Use special results              |       :x:       |    :x:    |        :ok:        |             :x:              |         :x:          |        :x:         |         :x:          |        :x:         |    :x:    |
| **VIEWING**                      |                 |           |                    |                              |                      |                    |                      |                    |           |
| View check-in                    |      :ok:       |   :ok:    |        :ok:        |             :ok:             |         :ok:         |        :ok:        |         :ok:         |        :ok:        |   :ok:    |
| View pairings                    |      :ok:       |   :ok:    |        :ok:        |             :ok:             |         :ok:         |        :ok:        |         :ok:         |        :ok:        |   :ok:    |
| View results                     |      :ok:       |   :ok:    |        :ok:        |             :ok:             |         :ok:         |        :ok:        |         :ok:         |        :ok:        |   :ok:    |

### Profiles

Profiles are defined on the web UI by:
- an IP address (the IP address of the machine accessing the _Sharly Chess_ server);
- credentials (a username and password, used to connect);
- an IP address and credentials.

### Giving roles to profiles

Profiles are given roles:
- statically: anybody connected on the _Sharly Chess_ server (``127.0.0.1```) is given the roles Administrator, Organizer and Chief Arbiter (this is locked);
- dynamically on the web UI for all the roles on all the clients except the _Sharly Chess itself.

In the example below:
- Connections from the server automatically have all roles (not configurable);
- Connections from the client ``192.168.1.115`` and authenticated with the username ``big-boss`` have the organization and chief referee roles for all tournaments;
- Connections authenticated with the usernames ``boss-1`` and ``boss-2`` have the arbiter role, for tournaments A/B and C/D respectively;
- The last two workstations allow check-in and results entry, respectively;
- Other unauthenticated clients can view the display screens.

|        |      Client       |      ID      |      Comment      | Tournament |   Administrator    |     Organizer      | Chief<br/>arbiter  | Deputy<br/>Chief<br/>arbiter |  Pairings<br/>Officer   |   Sector<br/>Arbiter    |  Check-in<br/>Officer   |   Result<br/>Officer    |        Spectator        |
|--------|:-----------------:|:------------:|:-----------------:|:----------:|:------------------:|:------------------:|:------------------:|:----------------------------:|:-----------------------:|:-----------------------:|:-----------------------:|:-----------------------:|:-----------------------:|
| :lock: |   ``127.0.0.1``   |      -       |      Server       |     -      | :white_check_mark: | :white_check_mark: | :white_check_mark: |   :ballot_box_with_check:    | :ballot_box_with_check: | :ballot_box_with_check: | :ballot_box_with_check: | :ballot_box_with_check: | :ballot_box_with_check: |
|        | ``192.168.1.115`` | ``big-boss`` |   Chief arbiter   |            |        :x:         |        :ok:        |        :ok:        |             :ok:             |          :ok:           |          :ok:           |          :ok:           |          :ok:           |          :ok:           |
|        |         -         |  ``boss-1``  |      Arbiter      |    A, B    |        :x:         |        :x:         |        :x:         |             :ok:             |          :ok:           |          :ok:           |          :ok:           |          :ok:           |          :ok:           |
|        |         -         |  ``boss-2``  |      Arbiter      |    C, D    |        :x:         |        :x:         |        :x:         |             :ok:             |          :ok:           |          :ok:           |          :ok:           |          :ok:           |          :ok:           |
|        | ``192.168.1.27``  |      -       | Check-in computer |            |        :x:         |        :x:         |        :x:         |             :x:              |          :ok:           |           :x:           |          :ok:           |          :ok:           |          :ok:           |
|        | ``192.168.1.226`` |      -       |  Result computer  |            |        :x:         |        :x:         |        :x:         |             :x:              |           :x:           |          :ok:           |          :ok:           |          :ok:           |          :ok:           |
| :lock: |         -         |      -       |                   |    :x:     |        :x:         |        :x:         |        :x:         |             :x:              |           :x:           |          :ok:           |                         |          :ok:           |          :ok:           |
