DROP VIEW IF EXISTS all_boards;

CREATE VIEW all_boards AS
WITH rating_override AS (
    SELECT
        p.id AS player_id,
        t.id AS tournament_id,
        CASE
            WHEN t.rating <> 1
              AND json_extract(p.ratings, '$.' || t.rating || '.type') <> 3
              AND coalesce(t.override_unrated_rapid_blitz, i.override_unrated_rapid_blitz) = 1
              AND json_extract(p.ratings, '$."1".type') <> 1
            THEN 1 ELSE 0
        END AS is_overridden,
        CASE
            WHEN t.rating <> 1
              AND json_extract(p.ratings, '$.' || t.rating || '.type') <> 3
              AND coalesce(t.override_unrated_rapid_blitz, i.override_unrated_rapid_blitz) = 1
              AND json_extract(p.ratings, '$."1".type') <> 1
            THEN json_extract(p.ratings, '$."1".value')
            ELSE json_extract(p.ratings, '$.' || t.rating || '.value')
        END AS effective_rating,
        CASE
            WHEN t.rating <> 1
              AND json_extract(p.ratings, '$.' || t.rating || '.type') <> 3
              AND coalesce(t.override_unrated_rapid_blitz, i.override_unrated_rapid_blitz) = 1
              AND json_extract(p.ratings, '$."1".type') <> 1
            THEN json_extract(p.ratings, '$."1".type')
            ELSE json_extract(p.ratings, '$.' || t.rating || '.type')
        END AS effective_rating_type
    FROM player p
    JOIN tournament_player tp ON tp.player_id = p.id
    JOIN tournament t ON t.id = tp.tournament_id
    JOIN info i ON i.ROWID = 1
)
SELECT
    -- BOARD
    p.tournament_id,
    p.round,
    COALESCE(
        LIKELY(NULLIF(wp.fixed, 0)),
        LIKELY(NULLIF(bp.fixed, 0)),
        b."index" + 1
    ) AS board_number,
    p.board_id,

    -- WHITE PLAYER
    wp.id AS white_id,
    wp.fide_id AS white_fide_id,
    wp.title AS white_title,
    wp.gender AS white_gender,
    CASE
        WHEN wp.first_name IS NULL OR wp.first_name = ''
            THEN wp.last_name
        ELSE wp.last_name || ', ' || wp.first_name
    END AS white_name,
    wp.federation AS white_federation,
    rw.effective_rating AS white_rating,
    rw.effective_rating_type AS white_rating_type,
    rw.is_overridden AS white_overridden,
    wp.plugin_data AS white_plugin_data,

    -- RESULTS
    p.result AS white_result,
    o.result AS black_result,

    -- BLACK PLAYER
    bp.id AS black_id,
    bp.fide_id AS black_fide_id,
    bp.title AS black_title,
    bp.gender AS black_gender,
    CASE
        WHEN bp.first_name IS NULL OR bp.first_name = ''
            THEN bp.last_name
        ELSE bp.last_name || ', ' || bp.first_name
    END AS black_name,
    bp.federation AS black_federation,
    rb.effective_rating AS black_rating,
    rb.effective_rating_type AS black_rating_type,
    rb.is_overridden AS black_overridden,
    bp.plugin_data AS black_plugin_data

FROM pairing p
LEFT JOIN board b
    ON p.board_id = b.id
   AND p.player_id = b.white_player_id
LEFT JOIN pairing o
    ON o.tournament_id = p.tournament_id
   AND o.round = p.round
   AND o.player_id = b.black_player_id
LEFT JOIN player wp ON wp.id = b.white_player_id
LEFT JOIN player bp ON bp.id = b.black_player_id
LEFT JOIN tournament t ON t.id = p.tournament_id
JOIN info i ON i.ROWID = 1
LEFT JOIN rating_override rw ON rw.player_id = wp.id AND rw.tournament_id = p.tournament_id
LEFT JOIN rating_override rb ON rb.player_id = bp.id AND rb.tournament_id = p.tournament_id;
