DROP VIEW IF EXISTS "all_players";
CREATE VIEW all_players AS
SELECT `player`.`id` as `player_id`,
`player`.`title`,
CASE
    WHEN `player`.`first_name` IS NULL OR `player`.`first_name` = '' THEN
        `player`.`last_name`
    ELSE
        `player`.`last_name` || ', ' || `player`.`first_name`
END as `name`,
`player`.`check_in`,
CASE
    WHEN `tournament`.`rating` <> 1
        AND json_extract(`players`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
        AND COALESCE(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
    THEN
        json_extract(`player`.`ratings`, '$.1.value')
    ELSE
        json_extract(`player`.`ratings`, '$.' || `tournament`.`rating` || '.value')
END as `rating`,
CASE
	WHEN `tournament`.`rating` <> 1
        AND json_extract(`player`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
        AND COALESCE(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
	THEN
		json_extract(`player`.`ratings`, '$.1.type')
	ELSE
		json_extract(`player`.`ratings`, '$.' || `tournament`.`rating` || '.type')
END as `rating_type`,
CASE
	WHEN `tournament`.`rating` <> 1
        AND json_extract(`player`.`ratings`, '$.' || `tournament`.`rating` || '.type') <> 3
        AND COALESCE(`tournament`.`override_unrated_rapid_blitz`, `info`.`override_unrated_rapid_blitz`) = 1
	THEN 1
    ELSE 0
END as `overridden`,
`player`.`federation`,
`player`.`club`, `player`.`date_of_birth`, `player`.`mail`, `player`.`phone`, `player`.`gender`,
`player`.`fixed`,
`player`.`fide_id`,
`player`.`owed`, `player`.`paid`,
`tournament`.`id` as `tournament_id`,
`player`.`comment`,
`player`.`plugin_data`,
json_group_array(
	CASE
		WHEN `board`.`white_player_id` = `player`.`id` THEN "W"
		WHEN `board`.`black_player_id` = `player`.`id` THEN "B"
		ELSE NULL
	END
) as `colors`,
json_group_array(`pairing`.`result`) as `results`,
json_group_array(
	CASE
		WHEN `board`.`white_player_id` = `player`.`id` THEN `board`.`black_player_id`
		WHEN `board`.`black_player_id` = `player`.`id` THEN `board`.`white_player_id`
		ELSE NULL
	END
) as `opponents`,
json_group_array(`pairing`.`board_id`) as `board_ids`
FROM `player`
LEFT JOIN `tournament_player` on `tournament_player`.`player_id` = `player`.`id`
LEFT JOIN `tournament` on (`tournament`.`id` = `tournament_player`.`tournament_id` AND `player`.`id` = `tournament_player`.`player_id`)
LEFT JOIN `pairing` ON (`pairing`.`player_id` = `player`.`id` AND `pairing`.`tournament_id` = `tournament`.`id`)
LEFT JOIN `board` ON `board`.`id` = `pairing`.`board_id`
JOIN `info` ON `info`.`ROWID` = 1
GROUP BY `player`.`id`;
