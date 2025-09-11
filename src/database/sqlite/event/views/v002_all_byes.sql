DROP VIEW IF EXISTS "all_byes";
CREATE VIEW "all_byes" AS
SELECT
-- PAIRING INFORMATION
`pairing`.`tournament_id`, `pairing`.`round`,

-- PLAYER INFORMATION
`player`.`id` AS `player_id`, `player`.`fide_id`, `player`.`title`,
CASE
    -- Only show the name in "LAST_NAME, First_Name" format if the first name is not empty
    WHEN `player`.`first_name` IS NULL OR `player`.`first_name` = '' THEN
        `player`.`last_name`
    ELSE
        `player`.`last_name` || ', ' || `player`.`first_name`
END AS `name`,
`player`.`federation`,
CASE
    -- when we are in a rapid or Blitz tournament (TournamentRating.STANDARD == 1 in the Pytho code)
	WHEN `tournament`.`rating` <> 1
        -- and the player's rating is not FIDE (RatingType.FIDE == 3 in the Python code)
		AND json_extract(`player`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
        -- and we override non-FIDE ratings (either ON tournament or using the default event-level option)
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
`player`.`plugin_data`,
`pairing`.`result` AS `result`
FROM `pairing`
LEFT JOIN `player` ON `player`.`id` = `pairing`.`player_id`
LEFT JOIN `tournament` ON `tournament`.`id` = `pairing`.`tournament_id`
-- There is only one info row per event.
JOIN `info` ON `info`.`ROWID` = 1
-- Only pairings without a board are games not scheduled.
-- However, this also includes the Pairing Allocated Bye so this is a special case
WHERE `pairing`.`board_id` IS NULL;
