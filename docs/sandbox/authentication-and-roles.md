# _Sharly Chess_ - Authorizations

> [!NOTE]
> This document is intended to move to the user documentation in version 3.1.

## Private / public networks

When starting the _Sharly Chess_ server, the administrator is asked if the networks are private or public:

- **The network I am connected to is private**
  (I control the devices that are allowed to connect and other devices can not connect, e.g. a Wi-Fi network protected by SSID/password):<br/>
  accessing the _Sharly Chess_ from the connected devices will be easy and safer.
- **The networks I am connected to is public**
  (devices connected to the network can not be trusted or can connect to the network without my authorization, e.g. a public Wi-Fi network):<br/>
  strong authentication will be asked to connect to the _Sharly Chess_ server.

> [!NOTE]
> The administrator is asked on startup only when the networks (IP addresses) changed since the last startup.

> [!NOTE]
> - Pascal: OK (Note: if several networks, the administrator should be asked if all the networks are private, or asked for each of the networks, but this is too complex)
> - Sammy: NOK
>> For Avoine, I had a network called "CULTUREL PRIVE", provided by the city of Avoine, that was technically closed, but anyone with the password could connect to. Is that a private or a public network? If it's a public network, then basically all big events--which are the only ones which definitely need the roles--will be on public events.
>> Furthemore, a malicious network administrator can change the network config mid-event. Is this in our threat model?
> - Timothy: OK/NOK
> - Youri: OK/NOK

## Execution modes

Two execution modes are possible, set at event-level (for each event):

- **Standard (by default)**: default permissions are assigned to the devices connected to the network.
- **Custom**: roles (fixed set of permissions) are customized.

Whatever the execution mode of the event, administrators (connected to the _Sharky Chess_) server have full privileges.

> [!NOTE]
> - Pascal: OK
> - Sammy: OK
> - Timothy: OK/NOK
> - Youri: OK/NOK

## Standard mode

The other devices connected to the network can:
- display the public screens;
- check-in players or enter results on the public screens proposed by the administrator.

> [!NOTE]
> Administrators who do not want to let devices check-in players or enter results do not propose the corresponding screens.

> [!NOTE]
> - Pascal: OK
> - Sammy: OK
> - Timothy: OK/NOK
> - Youri: OK/NOK

## Roles (custom mode only)

The roles are used only when the custom mode is selected, they offer a powerful way to customize the authorizations granted to accounts and devices.

A role:
- is a **fixed** set of permissions;
- inherit the permissions of sub-roles.

> [!NOTE]
> - Pascal: OK
> - Sammy: NOK
>> Roles != permissions
> - Timothy: OK/NOK
> - Youri: OK/NOK

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

> [!NOTE]
> - Pascal: OK
> - Sammy: NOK
>> RES is not a role, it's a set of permissions, same for CHE.
> - Timothy: OK/NOK
> - Youri: OK/NOK

## Custom mode

By default (when setting the custom mode), the devices connected have the same privileges as in standard mode (roles _Check-in_ and _Results entry_).

> [!NOTE]
> Administrators who do not want to let devices check-in players or enter results can revoke the corresponding roles (_Check-in_ and _Results entry_) to unknown devices, they can even revoke the _Spectator_ roles).

In custom mode, roles can be granted to accounts and devices.

> [!NOTE]
> - Pascal: OK
> - Sammy: OK
> - Timothy: OK/NOK
> - Youri: OK/NOK

## Accounts

Accounts are declared on the _Sharly Chess_ server by authorized people (ADM, ORG and CA, see below):
- a username (letters, numbers, ``_`` and ``-`` accepted);
- a mandatory password.

Unauthenticated accounts are named "anonymous" (roles can be granted to anonymous, e.g. _Spectator_).

> [!NOTE]
> - Pascal: OK
> - Sammy: OK
> - Timothy: OK/NOK
> - Youri: OK/NOK

### Authentication for accounts

Account authentication is stronger on public networks than on private networks:

- on private networks, **to be completed**
- on public networks, **to be completed**

> [!NOTE]
> On public networks, enhanced security prevents man-in-the-middle attacks.

> [!NOTE]
> - Pascal: waiting for proposals
> - Sammy: awaiting specification
> - Timothy: OK/NOK
> - Youri: OK/NOK

### Roles for accounts

On any network (public or private), any role can be granted or revoked to accounts (except _Administration_).

> [!NOTE]
> - Pascal: OK
> - Sammy: OK
> - Timothy: OK/NOK
> - Youri: OK/NOK

### Examples

| :unlock:/:lock: |        User        | Comment           | Roles |
|:---------------:|:------------------:|:------------------|:-----:|
|                 |    ``arbiter``     | The Chief Arbiter |  CA   |
|     :lock:      |   ``anonymous``    | _Unauthenticated_ |  SPE  |

> [!NOTE]
> - Pascal: OK
> - Sammy: NOK I don't understand the table
> - Timothy: OK/NOK
> - Youri: OK/NOK

## Devices

Devices are declared on the _Sharly Chess_ server by authorized people (ADM, ORG and CA, see below):
- an IP address.

Unauthenticated devices are named "unknown devices" (roles can be granted to unknown devices, e.g. _Spectator_).

> [!NOTE]
> - Pascal: OK
> - Sammy: OK
> - Timothy: OK/NOK
> - Youri: OK/NOK

### Authentication for devices

On public networks, authentication is not possible for devices: all the devices except the _Sharly Chess_ server are unknown devices.

On private networks, devices are authenticated by:
- **to be completed**

> [!NOTE]
> - Pascal: waiting for proposals
> - Sammy: awaiting specification
> - Timothy: OK/NOK
> - Youri: OK/NOK

### Roles for devices

Any device (authenticated or unknown) can be granted limited roles, up to _Check-in_ and _Results entry_.

> [!NOTE]
> - Pascal: OK
> - Sammy: NOK
>> Those are permissions, not roles. I also used devices with PAI-level permissions during Avoine because repeated authentication with changing IP addresses was a pain. While I understand the need to lower priviledge, I don't understand why arbiters can't give specific devices more permissions
> - Timothy: OK/NOK
> - Youri: OK/NOK

### Examples

| :unlock:/:lock: |      Device       | Comment                                           | Roles |
|:---------------:|:-----------------:|:--------------------------------------------------|:-----:|
|     :lock:      |   ``127.0.0.1``   | The server itself                                 |  ADM  |
|                 | ``192.168.1.115`` | A local device (allowed on private networks only) |  CHE  |
|     :lock:      |    ``0.0.0.0``    | Any (unknown) device                              |  SPE  |

> [!NOTE]
> - Pascal: OK
> - Sammy: NOK
>> I don't understand what the table aims to illustrate.
> - Timothy: OK/NOK
> - Youri: OK/NOK

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

> [!NOTE]
> - Pascal: OK
> - Sammy: OK/NOK
> - Timothy: OK/NOK
> - Youri: OK/NOK

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

> [!NOTE]
> - Pascal: OK
> - Sammy: OK/NOK
> - Timothy: OK/NOK
> - Youri: OK/NOK
