DROP VIEW IF EXISTS "all_byes";
CREATE VIEW "all_byes" as `SELECT` `pairing`.`tournament_id`, `pairing`.`round`,
`player`.`id` as `player_id`, `player`.`fide_id`, `player`.`title`,
CASE
    WHEN `player`.`first_name` IS NULL OR `player`.`first_name` = '' THEN
        `player`.`last_name`
    ELSE
        `player`.`last_name` || ', ' || `player`.`first_name`
END as `name`,
`player`.`federation`,
CASE
	WHEN `tournament`.`rating` <> 1
		AND json_extract(`player`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
		AND json_extract(`player`.`ratings`, '$.`1`.`type`') <> 1
		THEN
			json_extract(`player`.`ratings`, '$.`1`.`value`')
	ELSE
		json_extract(`player`.`ratings`, '$.' || `tournament`.`rating` || '.value')
END as `rating`,
CASE
	WHEN `tournament`.`rating` <> 1
		AND json_extract(`player`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
		AND json_extract(`player`.`ratings`, '$.`1`.`type`') <> 1
	THEN
		json_extract(`player`.`ratings`, '$.`1`.`type`')
	ELSE
		json_extract(`player`.`ratings`, '$.' || `tournament`.`rating` || '.type')
END as `rating_type`,
CASE
	WHEN `tournament`.`rating` <> 1
		AND json_extract(`player`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
		AND json_extract(`player`.`ratings`, '$.`1`.`type`') <> 1
	THEN 1
    ELSE 0
END as `overriden`,
`player`.`plugin_data`,
`pairing`.`result` as `result`
FROM `pairing`
LEFT JOIN `player` on `player`.`id` = `pairing`.`player_id`
LEFT JOIN `tournament` ON `tournament`.`id` = `pairing`.`tournament_id`
JOIN `info` on `info`.`ROWID` = 1
WHERE `pairing`.`board_id` IS NULL;
