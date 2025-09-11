DROP VIEW IF EXISTS "all_boards";
CREATE VIEW "all_boards" AS
-- BOARD DATA
SELECT `p`.`tournament_id`, `p`.`round`,
COALESCE(
    -- LIKELY is only an optimization hint, it does not affect the result of the computation.
    LIKELY(NULLIF(`white_player`.`fixed`, 0)),
    LIKELY(NULLIF(`black_player`.`fixed`, 0)),
    `board`.`index` + 1
) AS `board_number`,
`p`.`board_id`,

-- WHITE PLAYER'S DATA
`white_player`.`id` AS `white_id`,
`white_player`.`fide_id` AS `white_fide_id`,
`white_player`.`title` AS `white_title`,
`white_player`.`gender` AS `white_gender`,
CASE
    -- Only show the name in format "LAST_NAME, First_Name" if they have a non-empty first name
	WHEN `white_player`.`first_name` IS NULL or `white_player`.`first_name` = '' THEN
		`white_player`.`last_name`
	ELSE
		CONCAT(`white_player`.`last_name`, ', ', `white_player`.`first_name`)
END AS `white_name`,
`white_player`.`federation` AS `white_federation`,
CASE
    -- when we are in a rapid or Blitz tournament (TournamentRating.STANDARD == 1 in the Pytho code)
	WHEN `tournament`.`rating` <> 1
        -- and the player's rating is not FIDE (RatingType.FIDE == 3 in the Python code)
		AND json_extract(`white_player`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
        -- and we override non-FIDE ratings (either ON tournament or using the default event-level option)
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
        -- but only if the player is not estimated in standard rating (RatingType.ESTIMATED == 1)
		AND json_extract(`white_player`.`ratings`, '$.`1`.`type`') <> 1
		THEN
            -- then we override the rating with the player's standard rating
			json_extract(`white_player`.`ratings`, '$.`1`.`value`')
	ELSE
		json_extract(`white_player`.`ratings`, '$.' || `tournament`.`rating` || '.value')
END AS `white_rating`,
CASE
    -- see above, same reasoning
	WHEN `tournament`.`rating` <> 1
		AND json_extract(`white_player`.`ratings`,  '$.' || `tournament`.`rating` || '.type') <> 3
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
		AND json_extract(`white_player`.`ratings`, '$.`1`.`type`') <> 1
	THEN
		json_extract(`white_player`.`ratings`, '$.`1`.`type`')
	ELSE
		json_extract(`white_player`.`ratings`, '$.' || `tournament`.`rating` || '.type')
END AS `white_rating_type`,
CASE
    -- This an easier way to know if the player's rating was overridden, if this information needs displaying
	WHEN `tournament`.`rating` <> 1
		AND json_extract(`white_player`.`ratings`,  '$.' || `tournament`.`rating` || '.type') <> 3
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
		AND json_extract(`white_player`.`ratings`, '$.`1`.`type`') <> 1
	THEN 1
    ELSE 0
END AS `white_overridden`,
`white_player`.`plugin_data` AS `white_plugin_data`,

-- RESULTS
`p`.`result` AS `white_result`,
-- Note that black's result can be different from the opposite of white's result.
-- This is the case when one player gets a score penalty.
`o`.`result` AS `black_result`,

-- BLACK PLAYER'S DATA
`black_player`.`id` AS `black_id`,
`black_player`.`fide_id` AS `black_fide_id`,
`black_player`.`title` AS `black_title`,
`black_player`.`gender` AS `black_gender`,
CASE
-- See the white player's name for information
	WHEN `black_player`.`first_name` IS NULL OR `black_player`.`first_name` = '' THEN
		`black_player`.`last_name`
	ELSE
		CONCAT(`black_player`.`last_name`, ', ', `black_player`.`first_name`)
END AS `black_name`,
`black_player`.`federation` AS `black_federation`,
CASE
-- See the white player's rating for the reasoning
	WHEN `tournament`.`rating` <> 1
		AND json_extract(`black_player`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
		AND json_extract(`black_player`.`ratings`, '$.`1`.`type`') <> 1
    THEN
			json_extract(`black_player`.`ratings`, '$.`1`.`value`')
	ELSE
		json_extract(`black_player`.`ratings`, '$.' || `tournament`.`rating` || '.value')
END AS `black_rating`,
CASE
-- same as white player's rating type
	WHEN `tournament`.`rating` <> 1
		AND json_extract(`black_player`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
		AND json_extract(`black_player`.`ratings`, '$.`1`.`type`') <> 1
	THEN
		json_extract(`black_player`.`ratings`, '$.`1`.`type`')
	ELSE
		json_extract(`black_player`.`ratings`, '$.' || `tournament`.`rating` || '.type')
END AS `black_rating_type`,
CASE
	WHEN `tournament`.`rating` <> 1
		AND json_extract(`black_player`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
		AND json_extract(`black_player`.`ratings`, '$.`1`.`type`') <> 1
    THEN 1
    ELSE 0
END AS `black_overridden`,
`black_player`.`plugin_data` AS `black_plugin_data`
FROM `pairing` AS `p`
-- NOTE(Amaras): I have made the choice to only show one line per pairing, so the white player is "prioritized"
LEFT JOIN `board` ON (`p`.`board_id` = `board`.`id` AND `p`.`player_id` = `board`.`white_player_id`)
-- o for opponent: the black player's pairing
LEFT JOIN `pairing` AS `o` ON (`o`.`tournament_id` = `p`.`tournament_id` AND `o`.`round` = `p`.`round` AND `o`.`player_id` = `board`.`black_player_id`)
LEFT JOIN `player` AS `white_player` ON `white_player`.`id` = `board`.`white_player_id`
LEFT JOIN `player` AS `black_player` ON `black_player`.`id` = `board`.`black_player_id`
LEFT JOIN `tournament` ON `tournament`.`id` = `p`.`tournament_id`
-- There is only one line per event
JOIN `info` ON `info`.`ROWID` = 1;
