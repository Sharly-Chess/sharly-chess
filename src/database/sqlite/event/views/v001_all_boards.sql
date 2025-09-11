DROP VIEW IF EXISTS "all_boards";
CREATE VIEW all_boards AS
SELECT `p`.`tournament_id`, `p`.`round`,
COALESCE(LIKELY(NULLIF(`white_player`.`fixed`, 0)), LIKELY(NULLIF(`black_player`.`fixed`, 0)), `board`.`index` + 1) as `board_number`,
`p`.`board_id`,
`white_player`.`id` as `white_id`,
`white_player`.`fide_id` as `white_fide_id`,
`white_player`.`title` as `white_title`,
`white_player`.`gender` as `white_gender`,
CASE
	WHEN `white_player`.`first_name` IS NULL or `white_player`.`first_name` = '' THEN
		`white_player`.`last_name`
	ELSE
		CONCAT(`white_player`.`last_name`, ', ', `white_player`.`first_name`)
END as `white_name`,
`white_player`.`federation` as `white_federation`,
CASE
	WHEN `tournament`.`rating` <> 1
		AND json_extract(`white_player`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
		AND json_extract(`white_player`.`ratings`, '$.`1`.`type`') <> 1
		THEN
			json_extract(`white_player`.`ratings`, '$.`1`.`value`')
	ELSE
		json_extract(`white_player`.`ratings`, '$.' || `tournament`.`rating` || '.value')
END as `white_rating`,
CASE
	WHEN `tournament`.`rating` <> 1
		AND json_extract(`white_player`.`ratings`,  '$.' || `tournament`.`rating` || '.type') <> 3
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
		AND json_extract(`white_player`.`ratings`, '$.`1`.`type`') <> 1
	THEN
		json_extract(`white_player`.`ratings`, '$.`1`.`type`')
	ELSE
		json_extract(`white_player`.`ratings`, '$.' || `tournament`.`rating` || '.type')
END as `white_rating_type`,
CASE
	WHEN `tournament`.`rating` <> 1
		AND json_extract(`white_player`.`ratings`,  '$.' || `tournament`.`rating` || '.type') <> 3
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
		AND json_extract(`white_player`.`ratings`, '$.`1`.`type`') <> 1
	THEN 1
    ELSE 0
END as `white_overridden`,
`white_player`.`plugin_data` as `white_plugin_data`,
`p`.`result` as `white_result`,
`o`.`result` as `black_result`,
`black_player`.`id` as `black_id`,
`black_player`.`fide_id` as `black_fide_id`,
`black_player`.`title` as `black_title`,
`black_player`.`gender` as `black_gender`,
CASE
	WHEN `black_player`.`first_name` is NULL OR `black_player`.`first_name` = '' THEN
		`black_player`.`last_name`
	ELSE
		CONCAT(`black_player`.`last_name`, ', ', `black_player`.`first_name`)
END as `black_name`,
`black_player`.`federation` as `black_federation`,

CASE
	WHEN `tournament`.`rating` <> 1
		AND json_extract(`black_player`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
		AND json_extract(`black_player`.`ratings`, '$.`1`.`type`') <> 1
    THEN
			json_extract(`black_player`.`ratings`, '$.`1`.`value`')
	ELSE
		json_extract(`black_player`.`ratings`, '$.' || `tournament`.`rating` || '.value')
END as `black_rating`,
CASE
	WHEN `tournament`.`rating` <> 1
		AND json_extract(`black_player`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
		AND json_extract(`black_player`.`ratings`, '$.`1`.`type`') <> 1
	THEN
		json_extract(`black_player`.`ratings`, '$.`1`.`type`')
	ELSE
		json_extract(`black_player`.`ratings`, '$.' || `tournament`.`rating` || '.type')
END as `black_rating_type`,
CASE
	WHEN `tournament`.`rating` <> 1
		AND json_extract(`black_player`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
		AND coalesce(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
		AND json_extract(`black_player`.`ratings`, '$.`1`.`type`') <> 1
    THEN 1
    ELSE 0
END as `black_overridden`,
`black_player`.`plugin_data` as `black_plugin_data`
FROM `pairing` as `p`
LEFT JOIN `board` ON (`p`.`board_id` = `board`.`id` AND `p`.`player_id` = `board`.`white_player_id`)
LEFT JOIN `pairing` as `o` ON (`o`.`tournament_id` = `p`.`tournament_id` AND `o`.`round` = `p`.`round` AND `o`.`player_id` = `board`.`black_player_id`)
LEFT JOIN `player` as `white_player` ON `white_player`.`id` = `board`.`white_player_id`
LEFT JOIN `player` as `black_player` ON `black_player`.`id` = `board`.`black_player_id`
LEFT JOIN `tournament` ON `tournament`.`id` = `p`.`tournament_id`
JOIN `info` ON `info`.`ROWID` = 1;
