var polyglot = new Polyglot({
    locale: '{{ locale }}',
    phrases: {
        // Units
        'tc.moves':   '{{ _("<smart_count> move |||| <smart_count> moves") }}',
        'tc.min_abbr': '{{ _("min *** MINUTES") }}',
        'tc.sec_abbr': '{{ _("s *** SECONDS") }}',
        'tc.per_move': '{{ _("/move") }}',          // used like “+30 s/move”
        'tc.for_moves': '{{ _("/<moves>") }}',      // used like “90 min/40 moves”

        // Labels & joiners
        'tc.white': '{{ _("White") }}',
        'tc.black': '{{ _("Black") }}',
        'tc.then_join': '{{ _("<first> then <second>") }}',         // “A then B”
        'tc.comma_join': '{{ _("<first>, <second>") }}',            // “A, B”
        'tc.side_fmt': '{{ _("<side>: <text>") }}',                 // “White: …”
    },
    interpolation: {
        prefix: '<',
        suffix: '>',
    },
});

function tcMoves(n){ return polyglot.t('tc.moves', n); }

// Join array with localized commas and final “then”
function joinWithThenLocalized(parts){
    if (parts.length === 0) return '';
    if (parts.length === 1) return parts[0];

    // Fold with comma, then replace last join with “then”
    let out = parts[0];
    for (let i = 1; i < parts.length - 1; i++){
        out = polyglot.t('tc.comma_join', { first: out, second: parts[i] });
    }
    return polyglot.t('tc.then_join', { first: out, second: parts[parts.length-1] });
}

function fmtSecondsShort(total){
    // Prefer minutes if >= 60; otherwise seconds
    if (total >= 60 && total % 60 === 0) {
        const m = Math.floor(total/60);
        return `${m} ${polyglot.t('tc.min_abbr')}`;
    }
    if (total >= 60) {
        const m = Math.floor(total/60);
        const s = total % 60;
        return `${m} ${polyglot.t('tc.min_abbr')} ${s} ${polyglot.t('tc.sec_abbr')}`;
    }
    return `${total} ${polyglot.t('tc.sec_abbr')}`;
}

function humanizePeriodShort(p, idx, totalCount){
    const base = fmtSecondsShort(p.seconds || 0);
    const inc  = (p.increment != null && p.increment > 0)
        ? ` + ${p.increment} ${polyglot.t('tc.sec_abbr')}${polyglot.t('tc.per_move')}`
        : '';

    if (p.moves != null) {
        const movesStr = tcMoves(p.moves);
        const slashForMoves = polyglot.t('tc.for_moves', { moves: movesStr });
        return `${base}${slashForMoves}${inc}`;
    }
    return base + inc;
}

function humanizeSideShort(periods){
    if (!periods || !periods.length) return '';

    // Check if all increments are the same and non-null
    const increments = periods.map(p => p.increment ?? 0);
    const allEqual = increments.every(i => i === increments[0]);
    const commonInc = increments[0];

    // Build period strings without increment if shared
    const parts = periods.map((p,i) => {
        const base = fmtSecondsShort(p.seconds || 0);
        if (p.moves != null) {
            const movesStr = tcMoves(p.moves);
            const slashForMoves = polyglot.t('tc.for_moves', { moves: movesStr });
            return base + slashForMoves;
        }
        return base;
    });

    let out = parts.join(' {{ _('then') }} ');

    // Attach increment only once if shared
    if (allEqual && periods.length > 1 && commonInc > 0) {
        out += ` + ${commonInc} ${polyglot.t('tc.sec_abbr')}${polyglot.t('tc.per_move')} {{ _("from move 1") }}`;
    } else {
        const parts = periods.map((p,i) => humanizePeriodShort(p, i, periods.length));
        out = joinWithThenLocalized(parts);
    }

    return out;
}

// TRF25 → short string (handles asymmetry)
function humanizeTrf25Short(trf) {
    // If empty input, treat as not specified
    if (trf == null || String(trf).trim() === '') {
        return "{{ _('Not specified') }}";
    }

    try {
        const tc = parseTrf25(trf);

        // helper: a side is empty if no periods, or all periods have no moves/inc and 0 seconds
        const sideEmpty = (side) =>
            !Array.isArray(side) || side.length === 0 || side.every(p => (p.seconds|0) === 0 && p.moves == null && p.increment == null);

        if (sideEmpty(tc.white) && (!tc.black || sideEmpty(tc.black))) {
            return "{{ _('Not specified') }}";
        }

        const w = humanizeSideShort(tc.white);
        const b = tc.black ? humanizeSideShort(tc.black) : '';

        // If both render to empty strings, also not specified
        if ((!w || w.trim( '' ) === '') && (!b || b.trim( '' ) === '')) {
            return "{{ _('Not specified') }}";
        }

        if (b && b.trim() !== '' && w !== b) {
            const ws = polyglot.t('tc.side_fmt', { side: polyglot.t('tc.white'), text: w });
            const bs = polyglot.t('tc.side_fmt', { side: polyglot.t('tc.black'), text: b });
            return `${ws} / ${bs}`;
        }
        return w
    } catch (e) {
        // Any parse error → not specified
        return "{{ _('Not specified') }}";
    }
}

function parseTrf25(input) {
    const raw = String(input ?? '').trim();
    if (!raw) return { white: [{ seconds: 0 }] };

    // Allow only digits, W/B, / : + - and whitespace
    // (no quotes, letters, etc.)
    if (!/^[\s\dWwBb\/:\+\-]+$/.test(raw)) {
        throw new Error(`{{ _('Invalid TRF25 string: unexpected characters.') }}`);
    }

    const t = raw.replace(/\s+/g, ''); // TRF25 has no spaces

    const parseSide = (s) => s.replace(/^[WB]/i,'')
        .split(':').filter(Boolean).map(parsePeriod);

    function parsePeriod(tok) {
        const m = tok.match(/^(\d+\/)?(\d+)(?:\+(\d+))?$/);
        if (!m) throw new Error(`{{ _('Invalid period:') }} “${tok}”`);
        const moves = m[1] ? parseInt(m[1],10) : undefined;
        const seconds = parseInt(m[2],10);
        const increment = m[3] ? parseInt(m[3],10) : undefined;
        return { moves, seconds, increment };
    }

    if (/^[WB]/i.test(t) && t.includes('-')) {
        const [l, r] = t.split('-', 2);
        const out = {};
        (/^[Ww]/.test(l) ? (out.white = parseSide(l)) : (out.black = parseSide(l)));
        (/^[Bb]/.test(r) ? (out.black = parseSide(r)) : (out.white = parseSide(r)));
        return out;
    }
    return { white: parseSide(t) };
}

function formatTrf25(tc) {
    if (!tc || (!tc.white && !tc.black)) {
        return '';
    }

    const fmtSide = (side) => side.map(p => {
        const base = (p.moves != null ? p.moves + '/' : '') + (p.seconds ?? 0);
        return p.increment != null ? base + '+' + p.increment : base;
    }).join(':');

    const w = fmtSide(tc.white);
    const b = tc.black ? fmtSide(tc.black) : null;

    if (!w && !b) {
        return '';
    }
    if (w && b && w !== b) {
        return 'W' + w + '-B' + b;
    }
    return w;
}
