def parse_time_control_trf25(trf25: str | None) -> tuple[int, int]:
    """Parse time from TRF25 format. Returns (0, 0) for multi-period or asymmetric formats."""
    if not trf25:
        return 0, 0

    try:
        # Handle format: <secs> or <secs>+<inc>
        if '+' in trf25:
            parts = trf25.split('+')
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
            else:
                return 0, 0
        else:
            return int(trf25), 0
    except (ValueError, AttributeError):
        return 0, 0
