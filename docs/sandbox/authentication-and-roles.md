# _Sharly Chess_ - Authorizations

> [!NOTE]
> In version 2.4 (up to version 2.8), _Sharly Chess_ distinguishes two roles:
> - **the Arbitration role** (which is obtained by connecting from the server `127.0.0.1`), which can access:
>   - the administration pages, or arbitration pages;
>   - the public pages, with some additional privileges.
> - **the standard role**, which allows:
>   - to view public screens;
>   - to score and enter results (with or without password protection).
>
> This document will move to the user documentation in version 2.9.

## Execution modes

Three execution modes are possible:

- **Stand-alone (by default)**: You are the only one to manage your event, on the Sharly Chess server; other devices are not allowed to connect to your server.
- **Standard**: Other devices connected to your network can display screens, check-in players and enter results.
- **Custom**: authorizations for devices and users are based on roles.

The execution mode is set by default at application-level (for all the events) and can be overridden by the events.

## Roles

> [!IMPORTANT]
> The roles are used only when the custom mode is selected, they offer a powerful way to customize the authorizations granted to accounts and devices:

The roles in _Sharly Chess_ are:

- **Administration** (of the application): **ADM**
- **Organization** (of an event): **ORG**
- **Screen Management** (of an event): **SM**
- **Chief Arbitration** (of an event): **CA**
- **Deputy Chief Arbitration** (of an event): **DCA**
- **Pairing** (of tournaments): **PA**
- **Sector Arbitration** (of tournaments): **SA**
- **Result Entry** (of tournaments): **RE**
- **Check-in** (of tournaments): **CI**
- **Spectator** (of an event): **SP**

> [!NOTE]
> The arbiter roles are directly inspired by the FIDE hierarchical system:
> - The **Chief Arbiter** with admin-like rights over the event;
> - The **Deputy Chief Arbiter(s)** with lower rights over basically the whole event;
> - The **Sector Arbiter(s)** with rights over their sector (a sector being a set of tournaments);
> - The **Pairings Officer(s)** with full pairings management rights over a set of tournaments;
> - The Match Arbiter(s) - who can set results for their sector - are named **Results Officer** since this role may be assigned to players in _Sharly Chess_.
> In Continental and World events,
> - the CA, DCA and SA roles are mostly management positions (although they can intervene on games if Match Arbiters can't do it, of course), so they wouldn't play with the software once the rights are set up.
> - Pairings Officer are the ones doing the bulk of the work on the pairings software (especially in case of team tournaments)
> - Match Arbiters are focused on the games, so can enter results, but that's about it (although they should be able to correct wrong results).

Some roles 'include' other roles:
- Administration includes all the other roles (Administrators can do anything all the other roles can do);
- Organization includes Screen Management;
- Chief Arbitration includes Deputy Chief Arbitration;
- Deputy Chief Arbitration includes Sector Arbitration and Pairing;
- Sector Arbitration and Pairing includes Results Entry and Check-in;
- All the roles include Spectator.

## Devices

Devices are defined on the web UI by their IP address.

### Examples

| :unlock:/:lock: |      Device       | Comment           |
|:---------------:|:-----------------:|:------------------|
|     :lock:      |    ``0.0.0.0``    | Any device        |
|     :lock:      |   ``127.0.0.1``   | The server itself |
|                 | ``192.168.1.115`` | A local device    |

### Device roles

Devices can be given roles, without any other authentication.

> [!IMPORTANT]
> They must be trusted devices on a trusted network!

| :unlock:/:lock: |      Device       |        Comment         |        ADM         | ORG  |  SM  |  CA  |        DCA         |  PA  |  SA  |         CI         |         RE         |         SP         |
|:---------------:|:-----------------:|:----------------------:|:------------------:|:----:|:----:|:----:|:------------------:|:----:|:----:|:------------------:|:------------------:|:------------------:|
|     :lock:      |   ``127.0.0.1``   | Server (Chief Arbiter) | :white_check_mark: | :ok: | :ok: | :ok: |        :ok:        | :ok: | :ok: |        :ok:        |        :ok:        |        :ok:        |
|                 | ``192.168.1.100`` |  Deputy Chief Arbiter  |        :x:         | :x:  | :x:  | :x:  | :white_check_mark: | :ok: | :ok: |        :ok:        |        :ok:        |        :ok:        |
|                 | ``192.168.1.115`` |    Check-in device     |        :x:         | :x:  | :x:  | :x:  |        :x:         | :x:  | :x:  | :white_check_mark: |        :x:         |        :ok:        |
|                 | ``192.168.1.119`` |     Result device      |        :x:         | :x:  |      | :x:  |        :x:         | :x:  | :x:  |        :x:         | :white_check_mark: |        :ok:        |
|                 |    ``0.0.0.0``    |     Display device     |        :x:         | :x:  |      | :x:  |        :x:         | :x:  | :x:  |        :x:         |        :x:         | :white_check_mark: |

> [!NOTE]
> Connections from the server automatically have the Administration role (not configurable).

## Accounts

Users are defined by credentials (a unique username and an optional password).

### Examples

| :unlock:/:lock: |     User      | Comment           |
|:---------------:|:-------------:|:------------------|
|                 |  ``arbiter``  | The Chief Arbiter |
|                 | ``127.0.0.1`` | The server itself |
|                 |  ``0.0.0.0``  | _Unauthenticated_ |

> [!NOTE]
> No need to authenticate on the server, the Administration role is automatically given to the server.

### Account roles

Accounts can be given roles, after they authenticate.

| :unlock:/:lock: |      Device       |           Comment           | ADM  | ORG | SM  | CA  |        DCA         |  PA  |  SA  |         CI         |         RE         |         SP         |
|:---------------:|:-----------------:|:---------------------------:|:----:|:---:|:---:|:---:|:------------------:|:----:|:----:|:------------------:|:------------------:|:------------------:|
|                 |     ``mary``      |    Deputy Chief Arbiter     | :x:  | :x: | :x: | :x: | :white_check_mark: | :ok: | :ok: |        :ok:        |        :ok:        |        :ok:        |
|                 |     ``john``      | Check-in and Result Officer | :x:  | :x: | :x: | :x: |        :x:         | :x:  | :x:  | :white_check_mark: | :white_check_mark: |        :ok:        |
|                 |         -         |      _Unauthenticated_      | :x:  | :x: |     | :x: |        :x:         | :x:  | :x:  |        :x:         |        :x:         | :white_check_mark: |

## Permissions by role

|                                            |    ADM    |    ORG    |    SM     |    CA     |    DCA    |     PA     |     SA     |     CI     |     RE     |    SP     |     -     |
|--------------------------------------------|:---------:|:---------:|:---------:|:---------:|:---------:|:----------:|:----------:|:----------:|:----------:|:---------:|:---------:|
| **Scope**                                  | **Appl.** | **Event** | **Event** | **Event** | **Event** | **Tourn.** | **Tourn.** | **Tourn.** | **Tourn.** | **Event** | **Appl.** |
| **APPLICATION**                            |           |           |           |           |           |            |            |            |            |           |           |
| View application settings                  |   :ok:    |    n/a    |    n/a    |    n/a    |    n/a    |    n/a     |    n/a     |    n/a     |    n/a     |    n/a    |    :x:    |
| Update application settings                |   :ok:    |    n/a    |    n/a    |    n/a    |    n/a    |    n/a     |    n/a     |    n/a     |    n/a     |    n/a    |    :x:    |
| Grant/revoke Administration role           |    :x:    |    n/a    |    n/a    |    n/a    |    n/a    |    n/a     |    n/a     |    n/a     |    n/a     |    n/a    |    :x:    |
| Add events                                 |   :ok:    |    n/a    |    n/a    |    n/a    |    n/a    |    n/a     |    n/a     |    n/a     |    n/a     |    n/a    |    :x:    |
| Source databases management                |   :ok:    |    n/a    |    n/a    |    n/a    |    n/a    |    n/a     |    n/a     |    n/a     |    n/a     |    n/a    |    :x:    |
| View public current events                 |   :ok:    |    n/a    |    n/a    |    n/a    |    n/a    |    n/a     |    n/a     |    n/a     |    n/a     |    n/a    |  :ok:(*)  |
| View detailed event cards                  |   :ok:    |    n/a    |    n/a    |    n/a    |    n/a    |    n/a     |    n/a     |    n/a     |    n/a     |    n/a    |    :x:    |
| View private events                        |   :ok:    |    n/a    |    n/a    |    n/a    |    n/a    |    n/a     |    n/a     |    n/a     |    n/a     |    n/a    |    :x:    |
| View passed/coming events                  |   :ok:    |    n/a    |    n/a    |    n/a    |    n/a    |    n/a     |    n/a     |    n/a     |    n/a     |    n/a    |    :x:    |
| **EVENTS**                                 |           |           |           |           |           |            |            |            |            |           |           |
| Delete an event                            |   :ok:    |    :x:    |    :x:    |    :x:    |    :x:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Rename an event                            |   :ok:    |    :x:    |    :x:    |    :x:    |    :x:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Update an event                            |   :ok:    |   :ok:    |    :x:    |   :ok:    |    :x:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| View the complete event config             |   :ok:    |   :ok:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| View the basic event config                |   :ok:    |   :ok:    |   :ok:    |   :ok:    |   :ok:    |    :ok:    |    :ok:    |    :ok:    |    :ok:    |    :x:    |    :x:    |
| **ROLES**                                  |           |           |           |           |           |            |            |            |            |           |           |
| Manage Accounts                            |   :ok:    |   :ok:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Manage Devices                             |   :ok:    |   :ok:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Grant/revoke Organization role             |   :ok:    |    :x:    |    :x:    |    :x:    |    :x:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Grant/revoke Screen Management role        |   :ok:    |   :ok:    |    :x:    |    :x:    |    :x:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Grant/revoke Chief Arbitration role        |   :ok:    |   :ok:    |    :x:    |    :x:    |    :x:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Grant/revoke Deputy Chief Arbitration role |   :ok:    |    :x:    |    :x:    |   :ok:    |    :x:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Grant/revoke Sector Arbitration role       |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Grant/revoke Pairing role                  |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Grant/revoke Results Entry role            |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Grant/revoke Check-in role                 |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Update Spectators                          |   :ok:    |   :ok:    |   :ok:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| **TOURNAMENTS**                            |           |           |           |           |           |            |            |            |            |           |           |
| View Tournaments tab                       |   :ok:    |   :ok:    |   :ok:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Add tournaments                            |   :ok:    |    :x:    |    :x:    |   :ok:    |    :x:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Delete a tournament                        |   :ok:    |    :x:    |    :x:    |   :ok:    |    :x:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Update tournaments                         |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Publish results                            |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Publish rules                              |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Download fees                              |   :ok:    |   :ok:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| **PLAYERS**                                |           |           |           |           |           |            |            |            |            |           |           |
| View Players tab                           |   :ok:    |   :ok:    |   :ok:    |   :ok:    |   :ok:    |    :ok:    |    :ok:    |    :x:     |    :x:     |    :x:    |    :x:    |
| Add players                                |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Delete players                             |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Update players' information                |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Update players' record                     |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :ok:    |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| **CHECK-IN**                               |           |           |           |           |           |            |            |            |            |           |           |
| Open/close check-in                        |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Check-in players                           |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :ok:    |    :ok:    |    :x:     |    :x:    |    :x:    |
| **PAIRINGS**                               |           |           |           |           |           |            |            |            |            |           |           |
| Use the pairing engine                     |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :ok:    |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Unpair rounds                              |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :ok:    |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Manually pair players                      |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :ok:    |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Manually unpair boards                     |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :ok:    |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Set/unset Zero-Point Byes                  |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :ok:    |    :ok:    |    :ok:    |    :x:     |    :x:    |    :x:    |
| Set/unset Half-Point Byes                  |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :ok:    |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Set/unset Full-Point Byes                  |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| View draft pairings                        |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :ok:    |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Publish pairings                           |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| **RANKINGS**                               |           |           |           |           |           |            |            |            |            |           |           |
| View draft rankings                        |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Publish rankings                           |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| **RESULTS MANAGEMENT**                     |           |           |           |           |           |            |            |            |            |           |           |
| Enter results                              |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :ok:    |    :x:     |    :ok:    |    :x:    |    :x:    |
| Modify results                             |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Use special results                        |   :ok:    |    :x:    |    :x:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| **SCREENS**                                |           |           |           |           |           |            |            |            |            |           |           |
| Manage screens                             |   :ok:    |   :ok:    |   :ok:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Manage families                            |   :ok:    |   :ok:    |   :ok:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Manage rotators                            |   :ok:    |   :ok:    |   :ok:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Manage controllers                         |   :ok:    |   :ok:    |   :ok:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| Manage timers                              |   :ok:    |   :ok:    |   :ok:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| View private screens                       |   :ok:    |   :ok:    |   :ok:    |   :ok:    |   :ok:    |    :x:     |    :x:     |    :x:     |    :x:     |    :x:    |    :x:    |
| View public screens                        |   :ok:    |   :ok:    |   :ok:    |   :ok:    |   :ok:    |    :ok:    |    :ok:    |    :ok:    |    :ok:    |   :ok:    |    :x:    |

(*) Accessing the list of the public events is needed to authenticate (the accounts are defined at event-level).
