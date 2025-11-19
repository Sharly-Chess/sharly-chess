from dataclasses import dataclass
from typing import Optional, List


@dataclass
class TimePeriod:
    seconds: int
    increment: int = 0
    moves: Optional[int] = None


@dataclass
class TimeControl:
    white: List[TimePeriod]
    black: Optional[List[TimePeriod]] = None


def _parse_descriptor(desc: str) -> List[TimePeriod]:
    """
    Parse a single 'd' descriptor (std/all/inc) into one or more TimePeriod objects.
    Examples of desc:
        '5400+30'
        '40/6000+30:900+30'
        '300'
    """
    periods: List[TimePeriod] = []

    for part in desc.split(':'):
        part = part.strip()
        if not part:
            continue

        moves: Optional[int] = None

        # std: M/S or M/S+I
        if '/' in part:
            moves_str, rest = part.split('/', 1)
            moves = int(moves_str)
        else:
            rest = part

        # inc or all: S or S+I
        if '+' in rest:
            base_str, inc_str = rest.split('+', 1)
            seconds = int(base_str)
            increment = int(inc_str)
        else:
            seconds = int(rest)
            increment = 0

        periods.append(TimePeriod(seconds=seconds, increment=increment, moves=moves))

    return periods


def parse_time_control_trf25(time_control: str) -> TimeControl:
    """
    Parse a full TRF25 time control string into a TimeControl structure.

    Examples:
        '5400+30'
        '40/6000+30:900+30'
        'W300-B240'
    """
    s = time_control.strip()

    # Armageddon / colour-dependent form: Wd-Bd
    if s.startswith('W'):
        w_part, b_part = s.split('-', 1)

        if not (w_part.startswith('W') and b_part.startswith('B')):
            raise ValueError(f'Invalid W/B format: {s!r}')

        white_desc = w_part[1:]
        black_desc = b_part[1:]

        return TimeControl(
            white=_parse_descriptor(white_desc),
            black=_parse_descriptor(black_desc),
        )

    # Common form: d
    return TimeControl(white=_parse_descriptor(s))


def _format_seconds(seconds: int) -> str:
    """
    Format seconds as FIDE-style time: 90'  or  1'30"  or  30"
    """
    minutes, secs = divmod(seconds, 60)
    if minutes and secs:
        return f'{minutes}\'{secs}"'
    if minutes:
        return f"{minutes}'"
    return f'{secs}"'


def _format_period(p: TimePeriod) -> str:
    base = _format_seconds(p.seconds)
    inc = f'+{p.increment}"' if p.increment else ''
    if p.moves is not None:
        # e.g. 100' x40 +30"
        return f'{base}x{p.moves}{inc}'
    return f'{base}{inc}'


def format_time_control(tc: TimeControl) -> str:
    """
    Turn a TimeControl into a compact, language-light string.

    Examples out:
        5400+30          ->  90'+30"
        40/6000+30:900+30 -> 100'x40+30\" → 15'+30\"
        W300-B240        ->  White: 5'; Black: 4'
    """
    white_str = ' → '.join(_format_period(p) for p in tc.white)

    if tc.black is None:
        return white_str

    black_str = ' → '.join(_format_period(p) for p in tc.black)
    return f'White: {white_str}; Black: {black_str}'


def trf25_to_human_readable(s: str) -> str:
    """Convenience function."""
    return format_time_control(parse_time_control_trf25(s))
