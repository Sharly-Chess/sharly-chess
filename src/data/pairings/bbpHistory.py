from dataclasses import dataclass, field
from typing import List
from enum import IntEnum
import re

from utils.enum import BoardColor


class Floater(IntEnum):
    NONE = 0
    UP = 1
    DOWN = -1

    def __str__(self) -> str:
        match self:
            case Floater.UP:
                return '↑'
            case Floater.DOWN:
                return '↓'
            case Floater.NONE:
                return '·'
            case _:
                return str(self.value)


@dataclass
class ColorPreferenceData:
    """Color preference with strength indicators.
    Based on BBP format:
    - W/B: Absolute preference
    - (W)/(B): Strong preference
    - w/b: Mild preference
    - A: Any color (no preference)
    """

    color: BoardColor | None = None
    absolute: bool = False
    strong: bool = False


@dataclass
class TournamentHistoryPlayer:
    id: int  # pairing number
    points: float = 0.0
    color_history: List[BoardColor | None] = field(default_factory=list)
    color_preference: ColorPreferenceData | None = None
    eligible_for_bye: bool = False
    floater_prev: Floater | None = None
    floater_prev_prev: Floater | None = None
    current_opponent: int | None = None
    current_color: BoardColor | None = None
    previous_opponents: List[int | None] = field(default_factory=list)


@dataclass
class TournamentHistory:
    rounds: int
    players: List[TournamentHistoryPlayer] = field(default_factory=list)


def parse_color_preference(pref_str: str) -> ColorPreferenceData | None:
    pref_str = pref_str.strip()

    if pref_str == 'W':
        return ColorPreferenceData(color=BoardColor.WHITE, absolute=True, strong=False)
    elif pref_str == 'B':
        return ColorPreferenceData(color=BoardColor.BLACK, absolute=True, strong=False)
    elif pref_str == '(W)':
        return ColorPreferenceData(color=BoardColor.WHITE, absolute=False, strong=True)
    elif pref_str == '(B)':
        return ColorPreferenceData(color=BoardColor.BLACK, absolute=False, strong=True)
    elif pref_str == 'w':
        return ColorPreferenceData(color=BoardColor.WHITE, absolute=False, strong=False)
    elif pref_str == 'b':
        return ColorPreferenceData(color=BoardColor.BLACK, absolute=False, strong=False)
    else:
        return ColorPreferenceData(color=None, absolute=False, strong=False)


def parse_color_history(history_str: str) -> List[BoardColor | None]:
    colors: List[BoardColor | None] = []

    # Skip the first character (padding space) and process the rest
    history_chars = history_str[1:] if len(history_str) > 0 else ''

    for char in history_chars:
        if char == 'W':
            colors.append(BoardColor.WHITE)
        elif char == 'B':
            colors.append(BoardColor.BLACK)
        elif char == ' ':
            colors.append(None)

    return colors


def parse_bbp_checklist_text(text_content: str) -> TournamentHistory:
    """Parse the BBP Pairings checklist text format.
    Extracts: points, color preference, C2 (bye eligible), C12 (floater n-1),
    C14 (floater n-2), current opponent, and previous round opponents.
    """
    lines = text_content.split('\n')
    players_list = []
    header_found = False
    num_rounds = 0

    i = 0
    while i < len(lines):
        line = lines[i]

        # Look for header line that starts with "ID"
        if line.strip().startswith('ID\t'):
            header_found = True
            # Extract number of rounds from header
            # The color history column (index 2) has dashes = num_prev_rounds + 1
            header_parts = line.split('\t')
            if len(header_parts) > 2:
                color_history_header = header_parts[2].strip()
                # Count dashes in color history column header
                dash_count = color_history_header.count('-')
                num_rounds = dash_count - 1 if dash_count > 0 else 0
            else:
                num_rounds = 0
            i += 1
            continue

        # Skip empty lines and BBP footer
        if not line or line.startswith('BBP Pairings'):
            i += 1
            continue

        # Only parse player data if we found the header
        if not header_found:
            i += 1
            continue

        # Parse player data lines
        # Format: " 6\t2.0\t WB\t  w \t Y\t   \t   \t(16W)\t\t17\t15\t"
        # Columns: ID, Pts, [color_history], Pref, C2, C12, C14, Cur, [empty], R1, R2, ...
        parts = line.split('\t')
        if len(parts) >= 8:
            # First part should be player ID
            id_part = parts[0].strip()
            if not id_part or not id_part.isdigit():
                i += 1
                continue

            player_id = int(id_part)

            # Extract points (column 2)
            try:
                points = float(parts[1].strip())
            except (ValueError, IndexError):
                i += 1
                continue

            # Extract color history (column 3) - like "  WB", "   B", "    " (spaces = didn't play)
            try:
                history_raw = parts[2] if len(parts) > 2 else ''
                color_history = parse_color_history(history_raw)
            except IndexError:
                color_history = []

            # Extract color preference (column 4)
            try:
                pref_raw = parts[3].strip() if len(parts) > 3 else ''
                color_preference = parse_color_preference(pref_raw)
            except IndexError:
                color_preference = None

            # Extract C2 - eligible for bye (column 5)
            try:
                eligible_for_bye = parts[4].strip() == 'Y' if len(parts) > 4 else False
            except IndexError:
                eligible_for_bye = False

            # Extract C12 - floater round n-1 (column 6)
            floater_prev: Floater | None
            try:
                c12_value = parts[5].strip() if len(parts) > 5 else ''
                if c12_value == 'U':
                    floater_prev = Floater.UP
                elif c12_value == 'D':
                    floater_prev = Floater.DOWN
                else:
                    floater_prev = Floater.NONE
            except IndexError:
                floater_prev = Floater.NONE

            # Extract C14 - floater round n-2 (column 7)
            floater_prev_prev: Floater | None
            try:
                c14_value = parts[6].strip() if len(parts) > 6 else ''
                if c14_value == 'U':
                    floater_prev_prev = Floater.UP
                elif c14_value == 'D':
                    floater_prev_prev = Floater.DOWN
                else:
                    floater_prev_prev = Floater.NONE
            except IndexError:
                floater_prev_prev = Floater.NONE

            # Extract current opponent and color (column 8)
            current_opponent = None
            current_color = None
            try:
                cur_value = parts[7].strip() if len(parts) > 7 else ''
                # Format: "(16W)", "(22B)", etc.
                current_match = re.search(r'\((\d+)([WB])\)', cur_value)
                if current_match:
                    current_opponent = int(current_match.group(1))
                    color_char = current_match.group(2)
                    current_color = (
                        BoardColor.WHITE if color_char == 'W' else BoardColor.BLACK
                    )
            except IndexError:
                pass

            # Extract previous round opponents (columns 10 onwards, skipping empty column 9)
            # Process exactly num_rounds opponent columns (R1-R{num_rounds})
            previous_opponents: List[int | None] = []
            for round_idx in range(num_rounds):
                part = parts[9 + round_idx]
                stripped_part = part.strip()
                if stripped_part and stripped_part.isdigit():
                    previous_opponents.append(int(stripped_part))
                else:
                    previous_opponents.append(None)

            # Create player object
            player = TournamentHistoryPlayer(
                id=player_id,
                points=points,
                color_history=color_history,
                color_preference=color_preference,
                eligible_for_bye=eligible_for_bye,
                floater_prev=floater_prev,
                floater_prev_prev=floater_prev_prev,
                current_opponent=current_opponent,
                current_color=current_color,
                previous_opponents=previous_opponents,
            )

            players_list.append(player)

        i += 1

    # Sort by player ID
    players_list.sort(key=lambda p: p.id)

    return TournamentHistory(rounds=num_rounds, players=players_list)
