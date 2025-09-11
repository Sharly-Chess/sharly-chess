DROP VIEW IF EXISTS all_byes;

CREATE VIEW all_byes AS
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
    -- PAIRING
    pr.tournament_id,
    pr.round,

    -- PLAYER
    pl.id AS player_id,
    pl.fide_id,
    pl.title,
    CASE
        WHEN pl.first_name IS NULL OR pl.first_name = ''
            THEN pl.last_name
        ELSE pl.last_name || ', ' || pl.first_name
    END AS name,
    pl.federation,
    ro.effective_rating AS rating,
    ro.effective_rating_type AS rating_type,
    ro.is_overridden AS overridden,
    pl.plugin_data,

    -- RESULT
    pr.result
FROM pairing pr
LEFT JOIN player pl ON pl.id = pr.player_id
LEFT JOIN tournament t ON t.id = pr.tournament_id
JOIN info i ON i.ROWID = 1
LEFT JOIN rating_override ro
    ON ro.player_id = pl.id AND ro.tournament_id = pr.tournament_id
WHERE pr.board_id IS NULL;
