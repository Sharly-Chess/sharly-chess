# _Sharly Chess_ - Authorizations

> [!NOTE]
> This document is intended to move to the user documentation in version 3.1.

## ~~Private / public networks~~

~~When starting the _Sharly Chess_ server, the administrator is asked if the networks are private or public:~~

- ~~**The network I am connected to is private**
  (I control the devices that are allowed to connect and other devices can not connect, e.g. a Wi-Fi network protected by SSID/password):<br/>
  accessing the _Sharly Chess_ from the connected devices will be easy and safer.~~
- ~~**The networks I am connected to is public**
  (devices connected to the network can not be trusted or can connect to the network without my authorization, e.g. a public Wi-Fi network):<br/>
  strong authentication will be asked to connect to the _Sharly Chess_ server.~~

~~Note: The administrator is asked on startup only when the networks (IP addresses) changed since the last startup.~~

> **CLOSED**
>
> - Pascal: OK ~~(Note: if several networks, the administrator should be asked if all the networks are private, or asked for each of the networks, but this is too complex)~~<br/>
 **I do not agree but if I am the one it is OK: we do not talk about public or private networks anymore and I read Youri's point like this: user can grant any role.**<br/>
 @Sammy: if you read my definition of a private network above, "CULTUREL PRIVE" is public despite its name (but let's forget about it since all the networks are the same now).
> - Sammy: NOK<br/>
  For Avoine, I had a network called "CULTUREL PRIVE", provided by the city of Avoine, that was technically closed, but anyone with the password could connect to. Is that a private or a public network? If it's a public network, then basically all big events--which are the only ones which definitely need the roles--will be on public events.<br/>
  Furthermore, a malicious network administrator can change the network config mid-event. Is this in our threat model?
> - Youri: NOK<br/>
  Any question we add at the startup of the server is gonna be a pain for user experience, this is not a question that is enough important to do so (plus it can change mid-event).<br/>
  Suggestion 1: A network interface, with a checkbox 'Trust network' (not trusted by default, stored in the config).<br/>
  Suggestion 2 (preferred): Clear documentation in the roles tab that no important role (>= Sector Arbiter) should be granted if you are connected to a public network.
> - Timothy: NOK
  Too much of a pain for very few use cases.  I prefer Youri's solution 2.

## ~~Execution moeds~~ Permissions

~~Two execution modes are possible, set at event-level (for each event):~~
- ~~**Standard (by default)**: default permissions are assigned to the devices connected to the network.~~
- ~~**Custom**: roles (fixed set of permissions) are customized.~~

Remove sharks~~Whatever the execution mode of the event, administrators (connected to the _Sharly Chess_ server) have full privileges.~~

> **CLOSED**
>
> - Pascal: OK<br/>
  **I understand that you want to keep only the custom mode, initialized by default with the standard settings. I do agree (changes below), except with Youri's 'no device'.**<br/>
  @Youri: Standard is actually already the default mode, until you add your first access.
> - Sammy: OK
> - Youri: NOK<br/>
  If the interface is user-friendly enough (i.e. one tab, IMO no device), there is no need to have distinct execution modes just to hide the menu.<br/>
  Standard can simply be the default mode, until you've added your first access, with a clear doc (implemented like what is on families) stating what the default values are.
> - Timothy: NOK<br/>
  I hadn't considered Youri's solution, but I like it.

Permissions are set at event-level.

Default permissions are set at event creation and can be changed later at nay time.

## ~~Standard mode~~ Default permissions

Administrators (connected to the _Sharly Chess_ server) have full permissions.

The other devices connected to the network can:
- display the public screens;
- check-in players or enter results on the public screens proposed by the administrator.

> [!NOTE]
> Administrators who do not want to let devices check-in players or enter results do not propose the corresponding screens.

> **CLOSED**
>
> - Pascal: OK<br/>
  **So I renamed "Stand mode" to "Default permissions"**
> - Sammy: OK
> - Timothy: OK
> - Youri: OK<br/>
  OK with those permissions being the default.<br/>
  Suggestion: no auth possible if there are no account defined

## Roles ~~(custom mode only)~~

~~The roles are used only when the custom mode is selected, they offer a powerful way to customize the authorizations granted to accounts and devices.~~<br/>
Roles offer a powerful way to customize the authorizations granted to accounts and devices.

A role:
- is a **fixed** set of permissions;
- inherit the permissions of sub-roles.

> [!WARNING] **BETTER NAMING EXPECTED**
>
> - Pascal: OK<br/>
  @Sammy: you may have read too fast: roles are not permissions, they are fixed sets of permissions.<br/>
  Anyway I am not opposed to changing the names but what is the proposal (please something simple, not "set of permissions" because I used "roles" to have something simpler)?<br/>
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

## ~~Custom mode~~

~~By default (when setting the custom mode), the devices connected have the same privileges as in standard mode (roles _Check-in_ and _Results entry_).~~

> ~~[!NOTE]~~
> ~~Administrators who do not want to let devices check-in players or enter results can revoke the corresponding roles (_Check-in_ and _Results entry_) to unknown devices, they can even revoke the _Spectator_ roles).~~

~~In custom mode, roles can be granted to accounts and devices.~~

> **CLOSED**
>
> - Pascal: OK<br/>
  **I remove this part since custom mode does not exist anymore.<br/>
  @Timothy: I understand that you only want to keep two devices: server and unknown. see below.
  @Youri: It's all right the custom mode does exist anymore.
> - Sammy: OK
> - Timothy: NOK<br/>
  I think having devices is a mistake. Too complicated. OK with having a limited set available for unauthenticated machines.
> - Youri: OK<br/>
  OK with this being what you can do with roles, NOK with the concept of custom mode itself (see ## Execution modes)

## Accounts

Accounts are declared on the _Sharly Chess_ server by authorized people (ADM, ORG and CA, see below):
- a username (letters, numbers, ``_`` and ``-`` accepted);
- a mandatory password.

Unauthenticated accounts are named "anonymous" (roles can be granted to anonymous, e.g. _Spectator_).

> **CLOSED**
>
> - Pascal: OK
> - Sammy: OK
> - Timothy: OK
> - Youri: OK

### Authentication for accounts

~~Account authentication is stronger on public networks than on private networks:~~
~~- on private networks, **to be completed**~~
~~- on public networks, **to be completed**~~

~~> [!NOTE]~~
~~> On public networks, enhanced security prevents man-in-the-middle attacks.~~

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

~~On any network (public or private),~~ Any role can be granted or revoked to accounts (except _Administration_).

Limited roles can be granted to anonymous users (up to _Check-in_ and _Results entry_).

> **CLOSED**
>
> The limitation of the roles for the anonymous user has been moved from the device part.
>
> - Pascal: OK
> - Sammy: OK
> - Timothy: OK
> - Youri: OK

### Examples

| :unlock:/:lock: |     User      | Comment                | Roles                    |
|:---------------:|:-------------:|:-----------------------|:-------------------------|
|                 |  ``anneth``   | The Chief Arbiter      | CA                       |
|                 |   ``john``    | A deputy Chief Arbiter | DCA for some tournaments |
|     :lock:      | ``anonymous`` | _Unauthenticated_      | SPE                      |

> **CLOSED**
>
> - Pascal: OK<br/>
  @Sammy and @Youri: only examples of what the accounts of an event can be (feel free to add a sentence before the table if you feel it is necessary).
> - Sammy: NOK I don't understand the table
> - Timothy: OK, and this further removes any need for devices at all - just grant base permissions to authenticated connections.
> - Youri: not understood

## ~~Devices~~

~~Devices are declared on the _Sharly Chess_ server by authorized people (ADM, ORG and CA, see below):~~
- ~~an IP address.~~

~~The _Sharly Chess_ server has full access to everything.~~

~~Limited roles can be granted to all the other devices, without distinction (up to _Check-in_ and _Results entry_).~~

> [!WARNING] **NOT CLEAR**
>
> @Timothy and @Youri: I understand that you want to distinguish:
> - the _Sharly Chess_ server, with full access to everything
> - all the other devices, named authenticated.
> Text above changed accordingly below.
>
> **@Sammy are you OK with that (no IP declaration anymore)?**
>
> - Pascal: OK
> - Sammy: OK
> - Timothy:NOK<br/>
  I don't think this adds value.  The use-cases that I heard so far (headless etc) can all be achieved with an unauthenticated account.<br/>
  Anything that require more powerful permission should be username/password based.
> - Youri: NOK<br/>
  I strongly disagree with having devices in the app:<br/>
> - It complexifies the interface a lot<br/>
> - - users handling IPs<br/>
> - - double connection for the same user (device + account)<br/>
> - - twice the roles interface<br/>
> - IPs can change<br/>
> - It unclearly is much less secure than accounts<br/>
> - The advantages it currently has over accounts could be implemented into accounts<br/>
  Keeping connections alive: refresh tokens not revoked on startup<br/>
  IP restriction: could be a field in accounts, such that only these IPs would be allowed to connect to the account<br/>
> Trade security for an easier usage:<br/>
> - Unknown devices<br/>
> - Allowing passwordless accounts with a much longer refresh token (1d --> 7d)<br/>
  Both of these options have the advantage of being clearly not secure to users.<br/>
  I honestly can't see a good use-case (all the ones you've told me about are listed above), for a massive UX trade-off.

### ~~Authentication for devices~~

~~On public networks, authentication is not possible for devices: all the devices except the _Sharly Chess_ server are unknown devices.~~

~~On private networks, devices are authenticated by:~~
- ~~**to be completed**~~

> **CLOSED** (now out of purpose)
>
> - Pascal: waiting for proposals
> - Sammy: awaiting specification
> - Timothy: NOK
> We should not pretend to add security to an unsecure network.
> - Youri: username / password

### ~~Roles for devices~~

~~Any device (authenticated or unknown) can be granted limited roles, up to _Check-in_ and _Results entry_.~~

> **CLOSED**
>
> - Pascal: OK
> - Sammy: NOK<br/>
  Those are permissions, not roles. I also used devices with PAI-level permissions during Avoine because repeated authentication with changing IP addresses was a pain. While I understand the need to lower priviledge, I don't understand why arbiters can't give specific devices more permissions
> - Timothy: NOK
> OK with this for unauthenticated users
> - Youri: NOK

### ~~Examples~~

| :unlock:/:lock: |      ~~Device~~       | ~~Comment~~                                           | ~~Roles~~ |
|:---------------:|:---------------------:|:------------------------------------------------------|:---------:|
|     :lock:      |   ~~``127.0.0.1``~~   | ~~The server itself~~                                 |  ~~ADM~~  |
|                 | ~~``192.168.1.115``~~ | ~~A local device (allowed on private networks only)~~ |  ~~CHE~~  |
|     :lock:      |    ~~``0.0.0.0``~~    | ~~Any (unknown) device~~                              |  ~~SPE~~  |

> **CLOSED** (out of purpose)
>
> - Pascal: OK
> - Sammy: NOK<br/>
>> I don't understand what the table aims to illustrate.
> - Timothy: NOK
> - Youri: Not understood

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

> **CLOSED**
>
> - Pascal: OK
> - Sammy: OK/NOK
> - Timothy: OK
> - Youri: OK

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

> **CLOSED**
>
> - Pascal: OK
> - Sammy: OK/NOK
> - Timothy: Unreadable in my editor
> - Youri: OK (complex so might have missed something)
