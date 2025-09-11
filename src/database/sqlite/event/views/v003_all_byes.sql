DROP VIEW IF EXISTS all_byes;

CREATE VIEW all_byes AS
SELECT
    -- PAIRING
    pa.tournament_id,
    pa.round,

    -- PLAYER
    p.id AS player_id,
    p.fide_id,
    p.title,
    CASE
        WHEN p.first_name IS NULL OR p.first_name = ''
            THEN p.last_name
        ELSE p.last_name || ', ' || p.first_name
    END AS name,
    p.federation,
    pr.effective_rating AS rating,
    pr.effective_rating_type AS rating_type,
    pr.is_overridden AS overridden,
    p.plugin_data,

    -- RESULT
    pa.result
FROM pairing pa
LEFT JOIN player p ON p.id = pa.player_id
LEFT JOIN tournament t ON t.id = pa.tournament_id
JOIN info i ON i.ROWID = 1
LEFT JOIN player_effective_ratings pr ON pr.player_id = p.id AND pr.tournament_id = pa.tournament_id
WHERE pa.board_id IS NULL;
