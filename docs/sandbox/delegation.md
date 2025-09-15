# _Sharly Chess_ - Delegating event management

> [!NOTE]
> This document is intended to move to the user documentation in version 3.1.

## Access levels

Access levels offer a powerful way to customize the authorizations granted to the devices connected to your network.

An access level:
- is a **predefined** and **fixed** set of permissions;
- inherits the permissions of sub access levels.

The access levels in _Shary Chess_ are:

| Access level                          |    Scope    |
|---------------------------------------|:-----------:|
| ADM: Administration                   | Application |
| ORG: Organization                     |    Event    |
| SCR: Screen Management                |    Event    |
| CA: Chief Arbitration                 |    Event    |
| DCA: Deputy Chief Arbitration         | Tournament  |
| PAI: Pairing                          | Tournament  |
| SEC: Sector arbitration               | Tournament  |
| CHE: Check-in via public screens      | Tournament  |
| RES: Results Entry via public screens | Tournament  |
| SPE: Public screens view (Spectator)  |    Event    |

### Access levels inheritance

The diagram below shows the sub access levels each access level inherits from.

![Access levels inheritance](../images/access-levels-inheritance.jpg)

Access levels are set for each event.

Default access levels are set at event creation and can be changed later at any time.

### Default access levels

Administrators (connected to the _Sharly Chess_ server) have full privileges for the whole application, they can do anything on any event.

By default, unauthenticated devices connected to the network can:
- display the public screens;
- check-in players or enter results on the public screens.

> [!NOTE]
> It is possible to forbid unauthenticated devices from checking-in players or entering results by revoking the default access levels to unauthenticated devices.

## Accounts

### Definition

Accounts are defined for an event on the _Sharly Chess_ server by authorized people (ADM, ORG and CA, see below):
- an optional FIDE ID (unique at event-level);
- an optional first name;
- a mandatory last name;
- a password.

> [!NOTE]
> - When no password is set, authenticating with this account is nto possible.
> - When a password is deleted, devices authenticated with the account are disconnected (become unauthenticated devices).

### Unauthenticated devices

Unauthenticated devices are considered to be logged in with the special Anonymous account.

> [!NOTE]
> The Anonymous account can not be removed, only the access levels granted to the Anonymous account can be modified.

### Access levels for accounts

Accounts are granted access levels for the application, events or tournaments.

Any access level can be granted or revoked to accounts (except _Administration_).

Limited access levels can be granted to the Anonymous account (up to _Check-in_ and _Results entry_).

### Example

| FIDE ID     | First name    | Last name    | Comment                | Access levels            |
|:------------|:--------------|--------------|------------------------|:-------------------------|
| ``1234567`` | ``Charlotte`` | ``RAMPLING`` | The Chief Arbiter      | CA                       |
| ``9876543`` | ``John``      | ``WAYNE``    | A deputy Chief Arbiter | DCA for some tournaments |
| ``-``       | ``-``         | ``-``        | _Anonymous_            | SPE                      |

## Access levels management

The diagram below shows the access levels that can be managed by each access level.

| Access level                          |    Scope    | Sub<br/>access<br/>levels |   Inherited<br/>access<br/>levels   |      Manageable<br/>access<br/>levels       |
|---------------------------------------|:-----------:|:-------------------------:|:-----------------------------------:|:-------------------------------------------:|
| ADM: Administration                   | Application |        ORG<br/>CA         |                _all_                |                    _all_                    |
| ORG: Organization                     |    Event    |            SCR            |                 SPE                 |             SCR<br/>CA<br/>SPE              |
| SCR: Screen Management                |    Event    |            SPE            |               _none_                |                     SPE                     |
| CA: Chief Arbitration                 |    Event    |            DCA            | PAI<br/>SEC<br/>CHE<br/>RES<br/>SPE | DCA<br/>PAI<br/>SEC<br/>CHE<br/>RES<br/>SPE |
| DCA: Deputy Chief Arbitration         | Tournament  |            PAI            |     SEC<br/>CHE<br/>RES<br/>SPE     |                   _none_                    |
| PAI: Pairing                          | Tournament  |            SEC            |         CHE<br/>RES<br/>SPE         |                   _none_                    |
| SEC: Sector arbitration               | Tournament  |        CHE<br/>RES        |                 SPE                 |                   _none_                    |
| CHE: Check-in via public screens      | Tournament  |            SPE            |               _none_                |                   _none_                    |
| RES: Results Entry via public screens | Tournament  |            SPE            |               _none_                |                   _none_                    |
| SPE: Spectator                        |    Event    |          _none_           |               _none_                |                   _none_                    |

_Generated by script generate_access_levels_doc.py on 2025-08-19 16:36_

## Permissions by access level

The table below shows what each access level can do in the application.

| Permissions / Access levels       |                    |                    |                    |                    |                    |                    |                    |                    |                    |                    |                       |
|-----------------------------------|:------------------:|:------------------:|:------------------:|:------------------:|:------------------:|:------------------:|:------------------:|:------------------:|:------------------:|:------------------:|:---------------------:|
| APPLICATION MANAGEMENT            |        ADM         |        ORG         |        SCR         |         CA         |        DCA         |        PAI         |        SEC         |        CHE         |        RES         |        SPE         |        _none_         |
| View application settings         | :white_check_mark: |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |          :x:          |
| Update application settings       | :white_check_mark: |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |          :x:          |
| Manage source databases           | :white_check_mark: |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |          :x:          |
| EVENTS ACCESS                     |        ADM         |        ORG         |        SCR         |         CA         |        DCA         |        PAI         |        SEC         |        CHE         |        RES         |        SPE         |        _none_         |
| View public current events        | :white_check_mark: |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   | :white_check_mark:(*) |
| View private events               | :white_check_mark: |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |          :x:          |
| View passed and upcoming events   | :white_check_mark: |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |          :x:          |
| View event cards details          | :white_check_mark: |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |   :white_circle:   |          :x:          |
| EVENTS MANAGEMENT                 |        ADM         |        ORG         |        SCR         |         CA         |        DCA         |        PAI         |        SEC         |        CHE         |        RES         |        SPE         |        _none_         |
| Add events                        | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Delete events                     | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Rename events                     | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Update events                     | :white_check_mark: | :white_check_mark: |        :x:         | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| View complete event configuration | :white_check_mark: | :white_check_mark: |        :x:         | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| View basic event configuration    | :white_check_mark: | :white_check_mark: |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |          :x:          |
| ACCESS CONTROL                    |        ADM         |        ORG         |        SCR         |         CA         |        DCA         |        PAI         |        SEC         |        CHE         |        RES         |        SPE         |        _none_         |
| Manage accounts                   | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away access level ADM   |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away access level ORG   | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away access level SCR   | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away access level CA    | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away access level DCA   | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away access level PAI   | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away access level SEC   | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away access level CHE   | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away access level RES   | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away access level SPE   | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| TOURNAMENTS MANAGEMENT            |        ADM         |        ORG         |        SCR         |         CA         |        DCA         |        PAI         |        SEC         |        CHE         |        RES         |        SPE         |        _none_         |
| View the Tournaments tab          | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Add tournaments                   | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Update tournaments                | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Delete tournaments                | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Publish tournament results        | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Publish tournament rules          | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Download tournament fees          | :white_check_mark: | :white_check_mark: |        :x:         | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| PLAYERS                           |        ADM         |        ORG         |        SCR         |         CA         |        DCA         |        PAI         |        SEC         |        CHE         |        RES         |        SPE         |        _none_         |
| View Players tab                  | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |          :x:          |
| Add players                       | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Update players                    | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Update players' history           | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |          :x:          |
| Delete players                    | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| CHECK-IN                          |        ADM         |        ORG         |        SCR         |         CA         |        DCA         |        PAI         |        SEC         |        CHE         |        RES         |        SPE         |        _none_         |
| Open/close check-in               | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Check-in players                  | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |          :x:          |
| PAIRINGS                          |        ADM         |        ORG         |        SCR         |         CA         |        DCA         |        PAI         |        SEC         |        CHE         |        RES         |        SPE         |        _none_         |
| View Pairings tab                 | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |          :x:          |
| Use pairing engines               | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Manually pair players             | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Unpair all the boards of a round  | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Unpair one board                  | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Permute boards                    | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Set the current round             | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Set Zero-Points Byes              | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Set Half-Points Byes              | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Set Full-Points Byes              | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| View draft pairings               | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Publish pairings                  | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| RANKINGS                          |        ADM         |        ORG         |        SCR         |         CA         |        DCA         |        PAI         |        SEC         |        CHE         |        RES         |        SPE         |        _none_         |
| View draft rankings               | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Publish rankings                  | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| RESULTS                           |        ADM         |        ORG         |        SCR         |         CA         |        DCA         |        PAI         |        SEC         |        CHE         |        RES         |        SPE         |        _none_         |
| Enter results                     | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         | :white_check_mark: |        :x:         |          :x:          |
| Update results                    | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |          :x:          |
| Set illegal moves                 | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |          :x:          |
| Set special results               | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| SCREENS                           |        ADM         |        ORG         |        SCR         |         CA         |        DCA         |        PAI         |        SEC         |        CHE         |        RES         |        SPE         |        _none_         |
| Manage screens                    | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| View private screens              | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| View public screens               | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |          :x:          |
| PRIZES                            |        ADM         |        ORG         |        SCR         |         CA         |        DCA         |        PAI         |        SEC         |        CHE         |        RES         |        SPE         |        _none_         |
| View Prizes tab                   | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Manage prizes                     | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| PRINT                             |        ADM         |        ORG         |        SCR         |         CA         |        DCA         |        PAI         |        SEC         |        CHE         |        RES         |        SPE         |        _none_         |
| Print                             | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |

_Generated by script generate_access_levels_doc.py on 2025-08-19 16:31_

(*) Accessing the list of the public events is needed to authenticate (since the accounts are defined at event-level).
