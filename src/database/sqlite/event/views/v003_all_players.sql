DROP VIEW IF EXISTS "all_players";
CREATE VIEW all_players AS
-- PLAYER INFORMATION
SELECT `player`.`id` AS `player_id`,
`player`.`title`,
CASE
    -- Only show the name in "LAST_NAME, First_Name" format if the first name is not empty
    WHEN `player`.`first_name` IS NULL OR `player`.`first_name` = '' THEN
        `player`.`last_name`
    ELSE
        `player`.`last_name` || ', ' || `player`.`first_name`
END AS `name`,
`player`.`check_in`,
CASE
    -- when we are in a rapid or Blitz tournament (TournamentRating.STANDARD == 1 in the Pytho code)
	WHEN `tournament`.`rating` <> 1
        -- and the player's rating is not FIDE (RatingType.FIDE == 3 in the Python code)
		AND json_extract(`player`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
        -- and we override non-FIDE ratings (either on tournament or using the default event-level option)
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
        -- but only if the player is not estimated in standard rating (RatingType.ESTIMATED == 1)
		AND json_extract(`player`.`ratings`, '$.`1`.`type`') <> 1
		THEN
            -- then we override the rating with the player's standard rating
			json_extract(`player`.`ratings`, '$.`1`.`value`')
	ELSE
		json_extract(`player`.`ratings`, '$.' || `tournament`.`rating` || '.value')
END AS `rating`,
CASE
    -- see above, same reasoning
	WHEN `tournament`.`rating` <> 1
		AND json_extract(`player`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
		AND json_extract(`player`.`ratings`, '$.`1`.`type`') <> 1
	THEN
		json_extract(`player`.`ratings`, '$.`1`.`type`')
	ELSE
		json_extract(`player`.`ratings`, '$.' || `tournament`.`rating` || '.type')
END AS `rating_type`,
CASE
    -- This an easier way to know if the player's rating was overridden, if this information needs displaying
	WHEN `tournament`.`rating` <> 1
		AND json_extract(`player`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
		AND json_extract(`player`.`ratings`, '$.`1`.`type`') <> 1
	THEN 1
    ELSE 0
END AS `overriden`,
`player`.`federation`,
`player`.`club`, `player`.`date_of_birth`, `player`.`mail`, `player`.`phone`, `player`.`gender`,
`player`.`fixed`,
`player`.`fide_id`,
`player`.`owed`, `player`.`paid`,
`player`.`comment`,
`player`.`plugin_data`,
-- TOURNAMENT INFORMATION
`tournament`.`id` AS `tournament_id`,
`tournament_player`.`pairing_number`,

-- GAMES INFORMATION

-- NOTE(Amaras): In the examples below, I will show only two rounds of the objects.
-- I will take a random example: a player loses their round 1 game with black against the player with ID 67
-- and is given the PAB in round 2, the rest is not that interesting for this example.

-- colors == {"1": "B", "2": NULL, ...}
json_group_object(
    `pairing`.`round`,
	CASE
		WHEN `board`.`white_player_id` = `player`.`id` THEN "W"
		WHEN `board`.`black_player_id` = `player`.`id` THEN "B"
		ELSE NULL
	END
) AS `colors`,
-- results == {"1": 1, "2": 9, ...}
json_group_object(`pairing`.`round`, `pairing`.`result`) AS `results`,
-- opponents = {"1": 67, "2": NULL, ...}
json_group_object(
    `pairing`.`round`,
	CASE
		WHEN `board`.`white_player_id` = `player`.`id` THEN `board`.`black_player_id`
		WHEN `board`.`black_player_id` = `player`.`id` THEN `board`.`white_player_id`
		ELSE NULL
	END
) AS `opponents`,
-- board_ids == {"1": 276, "2": NULL, ...}
json_group_object(`pairing`.`round`, `pairing`.`board_id`) AS `board_ids`

FROM `player`
LEFT JOIN `tournament_player` ON `tournament_player`.`player_id` = `player`.`id`
LEFT JOIN `tournament` ON (`tournament`.`id` = `tournament_player`.`tournament_id` AND `player`.`id` = `tournament_player`.`player_id`)
LEFT JOIN `pairing` ON (`pairing`.`player_id` = `player`.`id` AND `pairing`.`tournament_id` = `tournament`.`id`)
LEFT JOIN `board` ON `board`.`id` = `pairing`.`board_id`
-- There is only one info row per event
JOIN `info` ON `info`.`ROWID` = 1
-- json_group_object is an aggregation function, so there needs to be a GROUP BY clause
GROUP BY `player`.`id`;
