# _Sharly Chess_ - Pairing actions

This page provides an overview of the actions in the tournaments, players, and pairings tabs.

## Round status definition

| Round                | Definition                                                                                | FR                                 |
|----------------------|-------------------------------------------------------------------------------------------|------------------------------------|
| Current round        | The last round with pairings                                                              | Ronde courante (ou ronde en cours) |
| Previous round       | The round immediately preceding the current round (N-1)                                   | Ronde précédente                   |
| Past rounds          | The rounds preceding the previous round (N-2, N-3, ...)                                   | Rondes passées                     |
| Next round           | The round immediately following the current round (N+1)                                   | Ronde suivante                     |
| Future rounds        | The rounds following the next round (N+2, N+3, ...)                                       | Rondes futures                     |
| Last published round | The last round for which the chief arbiter changed the status from "draft" to "published" | Dernière ronde publiée             |

{: .note }
> :information_source:
> - The concept of **last published round** does not yet exist and will be implemented when Access storage is discontinued.
> In the current version, all rounds with pairings are considered published (draft status does not exist).
> - The concepts in the table below are tournament-specific. The concept of a displayed or selected round is relative to the web interface; it is the active round in the Pairings tab.

## Tournament modifications

To be completed (some tournament modifications should not be allowed after a tournament has started).

## Player Modifications (Elo, FIDE title, or name)

{: .tip }
> :point_right: Changes to player information other than Elo, FIDE title, or name have no impact on pairings and ratings.

{: .note }
> :information_source:
> - _Papi_ recalculates pairing numbers every round (contrary to FIDE regulations).
> - Within a certain period of time after the publication of the results of round N (or before publication of the results), the change takes effect for the ratings of round N and the pairings of round N+1.
> After the publication of round N+1, the ratings are changed starting with round N+2.

| Time                                                           |  FIDE Authorized   |  Registration  | Recalculation<br/>numbers<br/>pairings |      Modification<br/>ratings       |
|----------------------------------------------------------------|:------------------:|:--------------:|:--------------------------------------:|:-----------------------------------:|
| Before publication of round 1 pairings                         | :white_check_mark: | :white_circle: |                round 1                 |                                     |
| Before publication of round 1 results                          | :white_check_mark: |   :pushpin:    |                round 2                 |               round 1               |
| After publication of round 2 pairings                          | :white_check_mark: |   :pushpin:    |                round 3                 |               round 3               |
| Before publication of round 2 results                          | :white_check_mark: |   :pushpin:    |                round 3                 |               round 2               |
| After publication of round 3 pairings                          | :white_check_mark: |   :pushpin:    |                round 4                 |               round 4               |
| Before the end of the publication deadline for round 3 results | :white_check_mark: |   :pushpin:    |                round 4                 |                                     |
| From the publication of round 4 pairings                       | :white_check_mark: |   :pushpin:    |                   no                   | round N+1 or N+2<br/>as appropriate |

{: .tip }
> :point_right: Compliance with FIDE regulations:
> - :white_check_mark: Action authorized by FIDE
>
> :point_right: Recording of non-standard actions:
> - :white_circle: No recording
> - :pushpin: Recording in the database

{: .warning }
> :warning: Sammy doit confirmer auprès de la DNA que le classement peut être modifié à n'importe quel moment car cela peut influer sur les départages.

## Editing Pairings and Results

An incorrect result or color in round N can be reported (FIDE regulations):
- Within a certain time after the publication of the results of round N
- The ratings of round N and the pairings of round N+1 use this correction
- After the publication of the pairings of round N+1, but before the end of round N+1
- The pairings of round N+2 use this correction (probably also the ratings of round N+1)
- After the end of round N+1
- The result is only used for the FIDE export, not for the final ratings or subsequent pairings.

### Action Descriptions

| Action / Round                |                     Past                      |                     Previous                      |                   Current                    |           First<br/>un<br/>paired            |                    Future                     |
|-------------------------------|:---------------------------------------------:|:-------------------------------------------------:|:--------------------------------------------:|:--------------------------------------------:|:---------------------------------------------:|
| Total Matching                | :no_entry_sign: :white_circle: :white_circle: |   :no_entry_sign: :white_circle: :white_circle:   | :white_circle: :white_circle: :white_circle: |      :white_check_mark: :ok: :pushpin:       | :no_entry_sign: :white_circle: :white_circle: |
| Complementary pairing         | :no_entry_sign: :white_circle: :white_circle: |   :no_entry_sign: :white_circle: :white_circle:   | :white_check_mark: :grey_question: :pushpin: | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle:  |
| Manual pairing                |      :no_entry_sign: :warning: :pushpin:      |   :white_check_mark: :grey_question: :pushpin:    | :white_check_mark: :grey_question: :pushpin: |     :no_entry_sign: :warning: :pushpin:      | :no_entry_sign: :white_circle: :white_circle: |
| Complete unpairing            | :no_entry_sign: :white_circle: :white_circle: |   :no_entry_sign: :white_circle: :white_circle:   |  :no_entry_sign: :grey_question: :pushpin:   | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle:  |
| Manual unpairing              |      :no_entry_sign: :warning: :pushpin:      |   :white_check_mark: :grey_question: :pushpin:    | :white_check_mark: :grey_question: :pushpin: | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle:  |
| Swap                          |      :no_entry_sign: :warning: :pushpin:      |   :white_check_mark: :grey_question: :pushpin:    | :white_check_mark: :grey_question: :pushpin: | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle:  |
| Editing a result              |      :no_entry_sign: :warning: :pushpin:      |   :white_check_mark: :grey_question: :pushpin:    |    :white_check_mark: :ok: :white_circle:    | :white_circle: :white_circle: :white_circle: | :white_circle: :white_circle: :white_circle:  |
| Modification of byes/packages |      :no_entry_sign: :warning: :pushpin:      | :ballot_box_with_check: :grey_question: :pushpin: | :ballot_box_with_check: :ok: :white_circle:  | :ballot_box_with_check: :ok: :white_circle:  |  :ballot_box_with_check: :ok: :white_circle:  |

{: .tip }
> :point_right: Compliance with FIDE regulations:
> - :white_circle: _Irrelevant action_
> - :no_entry_sign: Action not authorized by FIDE
> - :white_check_mark: Action authorized by FIDE
> - :ballot_box_with_check: Action authorized by FIDE, must be authorized by the regulations
> :point_right: Warning messages for arbiters:
> - :white_circle: _Action not proposed_
> - :ok: Action without warning message
> - :grey_question: Modal: The action you wish to perform is not "standard", continue?
> - :warning: Modal: The action you wish to perform is not authorized by FIDE, continue?
>
> :point_right: Recording of non-standard actions:
> - :white_circle: No record
> - :pushpin: Recording in the database
