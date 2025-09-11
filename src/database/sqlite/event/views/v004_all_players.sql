DROP VIEW IF EXISTS all_players;

CREATE VIEW all_players AS
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

    -- GAMES INFO

    -- colors == {"1": "B", "2": NULL, ...}
    json_group_object(
        pa.round,
        CASE
            -- the PAB has a board without an opponent, and has no color
            WHEN b.white_player_id = p.id AND b.black_player_id IS NOT NULL THEN 'W'
            WHEN b.black_player_id = p.id THEN 'B'
            ELSE NULL
        END
    ) AS colors,

    -- results == {"1": 1, "2": 9, ...}
    json_group_object(pa.round, pa.result) AS results,

    -- opponents = {"1": 67, "2": NULL, ...}
    json_group_object(
        pa.round,
        CASE
            WHEN b.white_player_id = p.id THEN b.black_player_id
            WHEN b.black_player_id = p.id THEN b.white_player_id
            ELSE NULL
        END
    ) AS opponents,

    -- board_ids == {"1": 276, "2": 485, ...}
    json_group_object(pa.round, pa.board_id) AS board_ids

FROM player p
LEFT JOIN tournament_player tp ON tp.player_id = p.id
LEFT JOIN tournament t ON t.id = tp.tournament_id
LEFT JOIN pairing pa ON pa.player_id = p.id AND pa.tournament_id = t.id
LEFT JOIN board b ON b.id = pa.board_id
LEFT JOIN player_effective_ratings pr ON pr.player_id = p.id AND pr.tournament_id = t.id

-- json_group_object is an aggregation function, so there needs to be a GROUP BY clause
GROUP BY p.id, t.id;
