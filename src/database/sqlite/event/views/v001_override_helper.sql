DROP VIEW IF EXISTS player_effective_ratings;

CREATE VIEW player_effective_ratings AS
SELECT
    tp.player_id,
    tp.tournament_id,

    CASE
        -- The rating is overridden when we are in a Rapid or Blitz tournament (TournamentRating.STANDARD == 1 in the Python code)
        WHEN t.rating <> 1
            -- and the player's rating is not FIDE (RatingType.FIDE == 3 in the Python code)
            AND json_extract(p.ratings, '$.' || t.rating || '.type') <> 3
            -- and we override non-FIDE ratings (either ON tournament or using the default event-level option)
            AND coalesce(t.override_unrated_rapid_blitz, i.override_unrated_rapid_blitz) = 1
            -- but only if the player has a FIDE standard rating
            AND json_extract(p.ratings, '$."1".type') = 3
        THEN 1 ELSE 0
    END AS is_overridden,

    CASE
    WHEN t.rating <> 1
        AND json_extract(p.ratings, '$.' || t.rating || '.type') <> 3
        AND coalesce(t.override_unrated_rapid_blitz, i.override_unrated_rapid_blitz) = 1
        AND json_extract(p.ratings, '$."1".type') = 3
    THEN json_extract(p.ratings, '$."1".value')
    ELSE json_extract(p.ratings, '$.' || t.rating || '.value')
    END AS effective_rating,

    CASE
    WHEN t.rating <> 1
        AND json_extract(p.ratings, '$.' || t.rating || '.type') <> 3
        AND coalesce(t.override_unrated_rapid_blitz, i.override_unrated_rapid_blitz) = 1
        AND json_extract(p.ratings, '$."1".type') = 3
    THEN json_extract(p.ratings, '$."1".type')
    ELSE json_extract(p.ratings, '$.' || t.rating || '.type')
    END AS effective_rating_type
FROM tournament_player tp
JOIN player p ON p.id = tp.player_id
JOIN tournament t ON t.id = tp.tournament_id
JOIN info i ON i.ROWID = 1;
