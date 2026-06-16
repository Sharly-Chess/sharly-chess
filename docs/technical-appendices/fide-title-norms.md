# FIDE Title Norms

Source: FIDE Handbook, `B.01` title regulations, effective from 1 January 2024: <https://handbook.fide.com/chapter/B012024>

This is a norm-focused reading note. It preserves FIDE article numbers, exact title names, exact thresholds, and key regulatory terms. Use the source page for the full official wording.

## 0.5 Definitions

Norm-related terms in article `0.5`:

| Term | Meaning for implementation/validation |
| --- | --- |
| Rating | Standard FIDE rating. |
| Rating performance | Based on the player's score and average opponent rating. See `1.4.6` to `1.4.8`. |
| Title performance | A performance result against the required minimum opponent average for the title. |
| Title norm | A title performance that also satisfies opponent title and federation mix rules in `1.4.2` to `1.4.5`. |

Title-performance thresholds from `0.5`:

| Performance | Required performance rating | Required opponent average |
| --- | ---: | ---: |
| GM | >= 2600 | >= 2380 |
| IM | >= 2450 | >= 2230 |
| WGM | >= 2400 | >= 2180 |
| WIM | >= 2250 | >= 2030 |

## 0.6 Award Of Titles

Article `0.6.3`: GM, IM, WGM, and WIM titles may be awarded by application after the player has norms with a sufficient number of games.

## 1.1 Administration Rules For Title Tournaments

Norm tournaments must satisfy these administration rules:

- `1.1.1`: Play uses FIDE Laws of Chess or the relevant Hybrid Chess regulations.
- `1.1.1`: Tournament format changes after the start require QC Chairperson approval.
- `1.1.1`: Players may not have different conditions for rounds and pairings.
- `1.1.1`: Unless approved otherwise, the tournament must be registered on the FIDE server at least 30 days before it starts.
- `1.1.2`: Maximum calculated play in one day is 12 hours, based on 60-move games.
- `1.1.3`: Maximum 2 rounds per day.
- `1.1.3`: Each player must have at least 2 hours for all moves, assuming a 60-move game.
- `1.1.3a`: For GM or WGM title applications based on norms, at least one norm must be from a tournament with one round per day for at least 3 days.
- `1.1.3b`: In a title tournament, time controls and clock settings must be identical for all games, except for the stated regulation exceptions.
- `1.1.4`: For tournaments longer than 30 days, opponent ratings and titles are those applying when the games were played.
- `1.1.5`: The Chief Arbiter must be IA or FA, and an IA or FA must always be in the playing venue.
- `1.1.6`: An appointed arbiter may not play in a title tournament.

## 1.2 Direct Titles And Single Norms From Championships

Article `1.2` covers titles and single norms from international championships. For these, the normal `1.4.2` to `1.4.9` requirements do not apply.

Useful norm-specific points:

- `1.2.1`: A player may gain a direct title or a single title norm from some listed events.
- `1.2.2`: Continental, sub-continental, and approved FIDE affiliate events need enough participating member federations.
- `1.2.2`: Minimum event size is 10 participants and 9 rounds, except for the stated disability championships exemption.
- `1.2.3`: In the direct-title tables, `Norm` means 9 games.
- `1.2.4`: Only events in the Table for Direct Titles can award titles under `1.2`.

## 1.4 Norm Route

Article `1.4`: GM, IM, WGM, and WIM can be gained by norms in FIDE-rated tournaments that satisfy the following rules.

## 1.4.1 Number Of Games

Normal rule:

- Minimum 9 games.

Exceptions and calculation rules:

- `1.4.1b`: 7 games are enough for 7-round World Team or Club and Continental Team or Club Championships.
- `1.4.1b`: 7 games are enough for 8- or 9-round World Team or Club and Continental Team or Club Championships.
- `1.4.1b`: 8 games are enough for the World Cup or Women's World Cup; those 8-game norms count as 9 games.
- `1.4.1c`: In a 9-round tournament, 8 played games can count as a 9-game norm if the missing game is due to forfeit win or pairing-allocated bye, the required opponent mix is met, and the player has a title result in those 8 games. Only one such norm may be used in a title application.
- `1.4.1d`: Each full point above the norm requirement counts as one extra game when calculating the total number of games for the achieved norm.
- `1.4.1e`: In tournaments with predetermined pairings, the norm must use all scheduled rounds.
- `1.4.1e`: In other tournaments, later games may be ignored after a title result has already been achieved, provided the opponent mix and minimum game count remain valid.
- `1.4.1f`: A player may ignore games against opponents they defeated, provided the remaining games still satisfy the opponent mix and minimum game count.
- `1.4.1f`: The complete crosstable must still be submitted.
- `1.4.1f`: For round-robin or double round-robin tournaments, the opponent mix must make a norm possible for the complete tournament.

## 1.4.2 Excluded Games And Formats

Do not include:

- `1.4.2a`: Games against opponents who do not belong to FIDE federations.
- `1.4.2a`: `FID` players are accepted, but do not count as foreign players.

**"Foreign" and `FID` (FIDE QC clarification, 2026).** "Foreign" means a
federation *different from the candidate's* — not different from the host
federation. And `FID` "is not considered a federation": `FID` players are
disregarded for every federation-mix rule. Concretely:

- A game against a `FID` opponent is still **accepted** — it counts
  towards games played, titled opponents, the rating average (`Ra`), and
  the score.
- But `FID` is **not** counted as one of the foreign federations under
  `1.4.3`, does **not** count towards `1.4.3d`'s "≥ 20 players not from
  the host federation" or "≥ 3 different federations", and cannot be the
  over-represented federation that breaches the `1.4.4` caps (so a field
  that is mostly `FID` does not violate the 2/3 one-federation cap).
- Exception: `RUS` and `BLR` players are displayed as `FID` but count
  under their own flag for norm purposes. The arbiter corrects the flag
  in the tournament data; the software then treats them as that
  federation, not as `FID`.
- `1.4.2b`: Games against unrated players who score zero against rated opponents in round-robin tournaments.
- `1.4.2c`: Games decided by forfeit, adjudication, or anything other than over-the-board play.
- `1.4.2d`: Tournaments changed to benefit one or more players, including changes to rounds, round order, or opponent assignment.

Started games are included. Under `1.4.2c`, a last-round opponent forfeit can still leave the norm valid if the player needed to play to reach the game count and could afford to lose.

Permitted formats under `1.4.2e`:

- Swiss.
- Round-Robin.
- Double Round-Robin.
- Knockout.

Other formats require prior QC Chairperson approval.

## 1.4.3 Opponent Federations

Normal rule:

- At least 2 opponent federations must be different from the applicant's federation.

Exemptions from that normal rule:

- `1.4.3a`: Final stage of national open/men's championship and national women's championship, subject to the regulation's zonal/sub-zonal limitation.
- `1.4.3b`: National team championships. The exemption applies only to players from the federation that registered the event, and results from different divisions cannot be combined.
- `1.4.3c`: Zonal and sub-zonal tournaments.
- `1.4.3d`: Swiss System tournaments in which participants include in every round at least 20 FIDE rated players, not from the host federation, from at least 3 different federations, at least 10 of whom hold GM, IM, WGM or WIM titles. For this purpose, players are counted only if they miss at most one round (excluding pairing-allocated byes). **Otherwise, `1.4.4` applies.**

All four exemptions (`1.4.3a`–`1.4.3d`) waive the **whole** foreigner
requirement — **both** `1.4.3` (foreign-federation count) AND `1.4.4`
(the 3/5 own-federation and 2/3 one-federation caps). This is the scope
defined by `1.4.3e`, which calls the combination of `1.4.3` and `1.4.4`
"the normal foreigner requirement", and by the chapeau of the article
("at least two federations … must be included, except `1.4.3a`–`1.4.3d`
shall be exempt"). The "Otherwise, `1.4.4` applies" clause inside
`1.4.3d` is what couples `1.4.4` to the exemption: when an exemption
holds, `1.4.4` stops applying; when `1.4.3d`'s tournament-wide
conditions are *not* met (and no `1.4.3a`–`1.4.3c` event-type exemption
applies), the normal `1.4.4` caps apply.

This was confirmed in writing by the FIDE Qualification Commission: the
national-championship and national-team-championship exemptions
(`1.4.3a` / `1.4.3b`), which apply only to players from the registering
federation, also waive `1.4.4`. Without this, a home player in an
all-domestic field (e.g. the French Interclubs) could never use the
exemption, because the 3/5 own-federation cap would always block them —
the exemption would be a dead letter for exactly the players it exists
to serve.

The application-level restriction is `1.4.3e`: across the norms making
up a full title application, at least one must be achieved under the
normal foreigner requirement (without any `1.4.3` exemption). That is a
multi-tournament concern handled at title-application time, not a
per-tournament norm check.

Important extra rule:

- `1.4.3e`: At least one norm in the title application must satisfy the normal foreign-player requirement.

## 1.4.4 Federation Maximums

Opponent federation limits (waived by any `1.4.3a`–`1.4.3d` exemption, as above):

- Maximum 3/5 of opponents may be from the applicant's federation.
- Maximum 2/3 of opponents may be from one federation.
- Minimum opponent counts are rounded up.
- Maximum opponent counts are rounded down.

Use the FIDE Annex for exact opponent counts by number of rounds.

## 1.4.5 Titled Opponents

General rule:

- At least 50% of opponents must be titleholders.
- CM and WCM do not count as titleholders for this rule.

Minimum titled-opponent requirements:

| Norm | Opponent title requirement |
| --- | --- |
| GM | At least one third of opponents, minimum 3, must be GMs. |
| IM | At least one third of opponents, minimum 3, must be IMs or GMs. |
| WGM | At least one third of opponents, minimum 3, must be WGMs, IMs, or GMs. |
| WIM | At least one third of opponents, minimum 3, must be WIMs, WGMs, IMs, or GMs. |

Double round-robin rule:

- Minimum 6 players.
- Required players with the necessary titles under `1.4.5b` to `1.4.5e` is half, rounded up.

Use the FIDE Annex for exact titled-opponent counts by number of rounds.

## 1.4.6 Opponent Ratings

Rating list:

- Use the rating list in effect at the start of the tournament, except for the `1.1.4` long-event rule.

Adjusted rating floors:

| Norm | Rating floor for one opponent |
| --- | ---: |
| GM | 2200 |
| IM | 2050 |
| WGM | 2000 |
| WIM | 1850 |

Floor rule:

- At most one opponent may have their rating raised to the adjusted rating floor.
- If more than one opponent is below the floor, raise the lowest-rated opponent.
- Unrated opponents not covered by `1.4.6b` count as 1400.

## 1.4.7 Opponent Average Rating

Calculation:

- Add opponents' ratings after applying `1.4.6`.
- Divide by the number of opponents.
- Round to the nearest whole number.
- `.5` rounds upward.

## 1.4.8 Performance Rating

Minimum performance levels:

| Norm | Minimum before rounding | Minimum after rounding |
| --- | ---: | ---: |
| GM | 2599.5 | 2600 |
| IM | 2449.5 | 2450 |
| WGM | 2399.5 | 2400 |
| WIM | 2249.5 | 2250 |

Formula:

```text
Rp = Ra + dp
```

Where:

- `Ra` is the opponent average from `1.4.7`.
- `dp` is the rating difference from the table in `1.4.9`.

Minimum average opponent ratings:

| Norm | Minimum `Ra` |
| --- | ---: |
| GM | 2380 |
| IM | 2230 |
| WGM | 2180 |
| WIM | 2030 |

Minimum score:

- 35% for all norms.

## 1.4.9 Performance Table

Article `1.4.9` gives the `p` to `dp` table used for `Rp = Ra + dp`.

Implementation note: do not recreate this table from memory. Use the official table or a tested FIDE performance implementation. Percentages are rounded to the nearest whole number, and `.5%` rounds upward.

## 1.5 Title Award After Norms

Requirements once norms have been achieved:

- `1.5.1`: Norms must cover at least 27 games.
- `1.5.2`: If a norm is sufficient for more than one title, it can be used for both applications.
- `1.5.4`: A title result is valid if it complied with the regulations in force when the norm was obtained.
- `1.5.5`: Norms gained before 1 July 2005 had to be registered by 31 July 2013.

Required rating:

| Title | Required rating |
| --- | ---: |
| GM | >= 2500 |
| IM | >= 2400 |
| WGM | >= 2300 |
| WIM | >= 2200 |

Rating details from `1.5.3a`:

- The rating does not have to be published.
- It can be reached during a rating period or during a tournament.
- The player may disregard later results for the title application.
- The applicant's federation has the burden of proof.
- Unpublished-rating applications require agreement from the Rating Administrator and the QC.
- Mid-period ratings can be confirmed only after all relevant tournaments have been received and rated by FIDE.

## 1.5.6 Mandatory Event Type For Post-2022 Applications

If an application includes at least one norm achieved after 30 June 2022, at least one norm must come from one of these:

- Individual Swiss tournament where every round has at least 40 participants and average rating at least 2000. Players count only if they miss at most one round, excluding pairing-allocated byes.
- Chess Olympiad.
- GSC event that establishes direct qualifiers to the FIDE Candidates Tournament.
- Tournament that establishes direct qualifiers to the FIDE World Cup.
- Individual tournament held under EVE regulations.
- Final stage of the National Individual Championship.

The listed championship-style events include open/men's and women's sections.

## 1.6 Summary Requirements

Article `1.6` is a summary. If it differs from earlier articles, the earlier regulation text controls.

Useful summary values:

| Requirement | Summary value | Article |
| --- | --- | --- |
| Rounds per day | Not more than 2 | `1.1.3` |
| Number of games | Minimum 9, with 7-game exceptions for certain World/Continental Team events | `1.4.1a-d` |
| GM titled opponents | One third, minimum 3 GMs | `1.4.5b` |
| IM titled opponents | One third, minimum 3 IMs | `1.4.5c` |
| WGM titled opponents | One third, minimum 3 WGMs | `1.4.5d` |
| WIM titled opponents | One third, minimum 3 WIMs | `1.4.5e` |
| Minimum performance | GM 2600; IM 2450; WGM 2400; WIM 2250 | `1.4.8` |
| Opponent average | GM 2380; IM 2230; WGM 2180; WIM 2030 | `1.4.8a` |
| Minimum score | 35% | `1.4.8b` |

## 1.7 Opponent Count Annex

Article `1.7` points to the Annex tables for exact opponent-count requirements up to 19 rounds.

Important implementation points:

- Whether a result is enough for a norm depends on the opponents' average rating.
- The Annex gives rating-average ranges by score and title.
- Norms from events longer than 13 rounds count only as 13 games.

## 1.8 Certificates

The Chief Arbiter prepares and signs the title-result certificate, then sends it to the organising federation's Rating Officer.

The Rating Officer or federation President checks and countersigns it, then sends signed copies to:

- the player's federation;
- the FIDE Office;
- the Chief Arbiter.

## 1.9 Reports

Tournament reports must include PGN:

- For Swiss and team tournaments: at least the games played by players who achieved title results.
- For other tournaments: all games.

## 1.10 Applications

Application procedure:

- Direct titles: Chief Arbiter sends the direct-title list to the FIDE Office.
- Titles by rating: the player's federation Rating Officer sends a request to FIDE.
- Titles by application: the application is sent and signed by the player's federation Rating Officer or President.
- Certificates must be signed by the Chief Arbiter and the Rating Officer or President of the federation responsible for the tournament.
- If the player's federation refuses to apply, the player can appeal to FIDE and apply directly.

Forms:

- GM, IM, WGM, WIM: `IT2`, `IT1s`.

Timing:

- Submit applications at least 45 days before the meeting where they will be considered.
- Applications and full details must be posted on the FIDE website for at least 30 days before finalisation.
