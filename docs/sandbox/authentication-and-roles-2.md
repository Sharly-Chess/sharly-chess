# _Sharly Chess_ - Authorizations

> [!NOTE]
> This document is intended to move to the user documentation in version 3.1.

## Permissions

Permissions are set at event-level.

Default permissions are set at event creation and can be changed later at nay time.

## Default permissions

Administrators (connected to the _Sharky Chess_ server) have full permissions.

The other devices connected to the network can:
- display the public screens;
- check-in players or enter results on the public screens proposed by the administrator.

> [!NOTE]
> Administrators who do not want to let devices check-in players or enter results do not propose the corresponding screens.

## Roles

Roles offer a powerful way to customize the authorizations granted to accounts and devices.

A role:
- is a **fixed** set of permissions;
- inherit the permissions of sub-roles.

> [!WARNING] **BETTER NAMING EXPECTED**
>
> - Pascal: I am OK with the roles as defined by sets of permissions, but I can look at better proposals.
> - Sammy: NOK<br/>
  Roles != permissions
> - Timothy: OK-ish As previously discussed, changing the name would be better. I'd like to reserve the term role for the staff tab, and call this something else (access level, privilege group, etc.)
> - Youri: OK

The roles in _Shary Chess_ are:

| Role                                  |    Scope    |
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
| SPE: Spectator                        |    Event    |

The diagram below shows the sub-roles each role inherits from.

![Roles inheritance](../images/roles-inheritance.jpg)

> [!WARNING] **BETTER NAMING EXPECTED**
>
> - Pascal: OK<br/>
  **Same as above: OK to change but change for what?**
> - Sammy: NOK
>> RES is not a role, it's a set of permissions, same for CHE.
> - Timothy: OK if name changed
> - Youri: OK

## Accounts

Accounts are declared on the _Sharly Chess_ server by authorized people (ADM, ORG and CA, see below):
- a username (letters, numbers, ``_`` and ``-`` accepted);
- a mandatory password.

Unauthenticated accounts are named "anonymous" (roles can be granted to anonymous, e.g. _Spectator_).

### Authentication for accounts

> [!WARNING] **AUTHENTICATION PROTOCOL EXPECTED**
>
> - Pascal: waiting for proposals<br/>
  @Sammy: if Youri's proposals are not OK please propose alternatives to save time. I do agree, these technical aspects should not be present in this doc, a dedicated functional documentation must be added apart from this documentation.<br/>
  @Timothy: OK, we do not distinguish public and private networks anymore.<br/>
  @@Youri: same, but OK, we do not distinguish public and private networks anymore.<br/>
> - Sammy: awaiting specification
> - Timothy: NOK<br/>
  No system that I know of adds any useful security to an unsecure network. What ever mechanism you use should be the same for all networks, and the arbiters should be educated.
> - Youri: Section only relevant if we identify networks.
>> - Suggestion 1: Longer refresh tokens.
>> - Suggestion 2 (preferred): Always consider connections from untrusted networks as unknown, and block auth.
>> - Suggestion 3: not identifying such networks.
>>
>> I also suggest we switch to `trusted / not trusted` instead of `private / public` in how we talk about it to the users, slightly less confusing.

**To be completed.**

### Roles for accounts

Any role can be granted or revoked to accounts (except _Administration_).

Limited roles can be granted to anonymous users (up to _Check-in_ and _Results entry_).

### Examples

| :unlock:/:lock: |     User      | Comment                | Roles                    |
|:---------------:|:-------------:|:-----------------------|:-------------------------|
|                 |  ``anneth``   | The Chief Arbiter      | CA                       |
|                 |   ``john``    | A deputy Chief Arbiter | DCA for some tournaments |
|     :lock:      | ``anonymous`` | _Unauthenticated_      | SPE                      |

> [!WARNING] **NOT CLEAR**
>
> @Timothy and @Youri: I understand that you want to distinguish:
> - the _Sharly Chess_ server, with full access to everything
> - all the other devices, named authenticated.
> Text above changed accordingly below.
>
> **@Sammy are you OK with that (no IP declaration anymore)?**

## Roles management

The diagram below shows the roles that can be managed by each role.

| Role                                  |    Scope    | Sub<br/>roles |         Inherited<br/>roles         |            Manageable<br/>roles             |
|---------------------------------------|:-----------:|:-------------:|:-----------------------------------:|:-------------------------------------------:|
| ADM: Administration                   | Application |  ORG<br/>CA   |                _all_                |                    _all_                    |
| ORG: Organization                     |    Event    |      SCR      |                 SPE                 |             SCR<br/>CA<br/>SPE              |
| SCR: Screen Management                |    Event    |      SPE      |               _none_                |                     SPE                     |
| CA: Chief Arbitration                 |    Event    |      DCA      | PAI<br/>SEC<br/>CHE<br/>RES<br/>SPE | DCA<br/>PAI<br/>SEC<br/>CHE<br/>RES<br/>SPE |
| DCA: Deputy Chief Arbitration         | Tournament  |      PAI      |     SEC<br/>CHE<br/>RES<br/>SPE     |                   _none_                    |
| PAI: Pairing                          | Tournament  |      SEC      |         CHE<br/>RES<br/>SPE         |                   _none_                    |
| SEC: Sector arbitration               | Tournament  |  CHE<br/>RES  |                 SPE                 |                   _none_                    |
| CHE: Check-in via public screens      | Tournament  |      SPE      |               _none_                |                   _none_                    |
| RES: Results Entry via public screens | Tournament  |      SPE      |               _none_                |                   _none_                    |
| SPE: Spectator                        |    Event    |    _none_     |               _none_                |                   _none_                    |

_Generated by script generate_roles_doc.py on 2025-08-19 16:36_

## Permissions by role

The table below shows what each role can do in the application.

| Permissions / Roles               |                    |                    |                    |                    |                    |                    |                    |                    |                    |                    |                       |
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
| Manage devices                    | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away role ADM           |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away role ORG           | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away role SCR           | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away role CA            | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away role DCA           | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away role PAI           | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away role SEC           | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away role CHE           | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away role RES           | :white_check_mark: |        :x:         |        :x:         | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
| Give/take away role SPE           | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |        :x:         |          :x:          |
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

_Generated by script generate_roles_doc.py on 2025-08-19 16:31_

(*) Accessing the list of the public events is needed to authenticate (since the accounts are defined at event-level).
