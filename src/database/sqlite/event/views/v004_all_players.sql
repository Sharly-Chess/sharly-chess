DROP VIEW IF EXISTS all_players;

CREATE VIEW all_players AS
WITH rating_override AS (
    SELECT
        tp.player_id,
        tp.tournament_id,
        CASE
            WHEN t.rating <> 1
              AND json_extract(p.ratings, '$.' || t.rating || '.type') <> 3
              AND coalesce(t.override_unrated_rapid_blitz, i.override_unrated_rapid_blitz) = 1
              AND json_extract(p.ratings, '$."1".type') <> 1
            THEN 1 ELSE 0
        END AS is_overridden
    FROM player p
    JOIN tournament_player tp ON tp.player_id = p.id
    JOIN tournament t ON t.id = tp.tournament_id
    JOIN info i ON i.ROWID = 1
)
SELECT
    -- PLAYER INFO
    p.id AS player_id,
    p.title,
    CASE
        WHEN p.first_name IS NULL OR p.first_name = '' THEN p.last_name
        ELSE p.last_name || ', ' || p.first_name
    END AS name,
    p.check_in,

    pr.effective_rating AS rating,
    pr.effective_rating_type AS rating_type,
    pr.is_overridden AS overridden,

    p.federation,
    p.club,
    p.date_of_birth,
    p.mail,
    p.phone,
    p.gender,
    p.fixed,
    p.fide_id,
    p.owed,
    p.paid,
    p.comment,
    p.plugin_data,

    -- TOURNAMENT INFO
    t.id AS tournament_id,
    tp.pairing_number,

    -- GAME INFO (per round JSON objects)
    json_group_object(
        pa.round,
        CASE
            WHEN b.white_player_id = p.id THEN 'W'
            WHEN b.black_player_id = p.id THEN 'B'
            ELSE NULL
        END
    ) AS colors,

    json_group_object(pa.round, pa.result) AS results,

    json_group_object(
        pa.round,
        CASE
            WHEN b.white_player_id = p.id THEN b.black_player_id
            WHEN b.black_player_id = p.id THEN b.white_player_id
            ELSE NULL
        END
    ) AS opponents,

    json_group_object(pa.round, pa.board_id) AS board_ids

FROM player p
LEFT JOIN tournament_player tp ON tp.player_id = p.id
LEFT JOIN tournament t ON t.id = tp.tournament_id
LEFT JOIN pairing pa ON pa.player_id = p.id AND pa.tournament_id = t.id
LEFT JOIN board b ON b.id = pa.board_id
JOIN info i ON i.ROWID = 1
LEFT JOIN player_effective_ratings pr ON pr.player_id = p.id AND pr.tournament_id = t.id

GROUP BY p.id, t.id;
