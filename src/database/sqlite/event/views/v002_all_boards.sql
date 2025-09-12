DROP VIEW IF EXISTS all_boards;

CREATE VIEW all_boards AS
SELECT
    -- BOARD
    pa.tournament_id,
    pa.round,
    COALESCE(
        LIKELY(NULLIF(wp.fixed, 0)),
        LIKELY(NULLIF(bp.fixed, 0)),
        b."index" + 1
    ) AS board_number,
    b."index" + 1 as board_index,
    pa.board_id,

    -- WHITE PLAYER
    wp.id AS white_id,
    wp.fide_id AS white_fide_id,
    wp.title AS white_title,
    wp.gender AS white_gender,
    CASE
        -- Only show the name in format "LAST_NAME, First_Name" if they have a non-empty first name
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
    pa.result AS white_result,
    -- Note that black's result can be different from the opposite of white's result.
    -- This is the case when one player gets a score penalty.
    o.result AS black_result,

    -- BLACK PLAYER
    -- NOTE(Amaras): this table includes the PAB, since a board is created for them, but without an opponent
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

FROM pairing pa
LEFT JOIN board b
    ON pa.board_id = b.id
   AND pa.player_id = b.white_player_id
LEFT JOIN pairing o
    ON o.tournament_id = pa.tournament_id
   AND o.round = pa.round
   AND o.player_id = b.black_player_id
LEFT JOIN player wp ON wp.id = b.white_player_id
LEFT JOIN player bp ON bp.id = b.black_player_id
LEFT JOIN tournament t ON t.id = pa.tournament_id
LEFT JOIN player_effective_ratings rw ON rw.player_id = wp.id AND rw.tournament_id = pa.tournament_id
LEFT JOIN player_effective_ratings rb ON rb.player_id = bp.id AND rb.tournament_id = pa.tournament_id
WHERE b.id IS NOT NULL AND b.white_player_id IS NOT NULL
