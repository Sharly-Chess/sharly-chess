# _Sharly Chess_ - Connecting devices to the server

This document focuses on technical aspects of connecting devices to the _Sharly Chess_ server, in addition to user documentation.
- [View the user documentation](https://sharly-chess.com/network)

- [View a simplified view of the permissions by access level](access-levels-permissions.md)

> [!NOTE]
> PA: IMO The rest of the documentation can be deleted now.

---

## Access levels

Access levels offer a powerful way to customize the authorizations granted to the devices connected to your network.

An access level:
- is a **predefined** and **fixed** set of permissions;
- inherits the permissions of sub access levels.

The access levels in _Shary Chess_ are:

| Access level                         |    Scope    |
|--------------------------------------|:-----------:|
| ADM Administration                   | Application |
| ORG Organization                     |    Event    |
| SCR Screen Management                |    Event    |
| CA Chief Arbitration                 |    Event    |
| DCA Deputy Chief Arbitration         | Tournament  |
| PAI Pairing                          | Tournament  |
| SEC Sector arbitration               | Tournament  |
| CHE Check-in via public screens      | Tournament  |
| RES Results Entry via public screens | Tournament  |
| SPE Spectator                        |    Event    |

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
- an optional FIDE ID (unique at event-level, from version 3.2, used for TRF exports);
- an optional first name;
- a mandatory last name;
- a password;
- a flag to enable/disable the account.

> [!NOTE]
> - It is impossible to authenticate with a disabled account.
> - When an account is disabled, devices authenticated with the account are disconnected (become unauthenticated devices).

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

| Access level                         |    Scope    | Sub access levels | Inherited access levels |   Manageable access levels   |
|:-------------------------------------|:-----------:|:-----------------:|:-----------------------:|:----------------------------:|
| ADM Administration                   | Application |      ORG, CA      |           all           |             all              |
| ORG Organization                     |    Event    |        SCR        |           SPE           |         SCR, CA, SPE         |
| SCR Screen Management                |    Event    |        SPE        |          none           |             SPE              |
| CA Chief Arbitration                 |    Event    |        DCA        | PAI, SEC, CHE, RES, SPE | DCA, PAI, SEC, CHE, RES, SPE |
| DCA Deputy Chief Arbitration         | Tournament  |        PAI        |   SEC, CHE, RES, SPE    |             none             |
| PAI Pairing                          | Tournament  |        SEC        |      CHE, RES, SPE      |             none             |
| SEC Sector arbitration               | Tournament  |     CHE, RES      |           SPE           |             none             |
| CHE Check-in via public screens      | Tournament  |        SPE        |          none           |             none             |
| RES Results entry via public screens | Tournament  |        SPE        |          none           |             none             |
| SPE Spectator                        |    Event    |       none        |          none           |             none             |

_Generated by script generate_access_levels_doc.py on 2025-09-16 20:54_
