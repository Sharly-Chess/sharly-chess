from pathlib import Path

from common import TMP_DIR
from common.logger import print_interactive_info
from common.tool_installer import BbpPairingsInstaller
from data.pairings.checkers import BbpPairingsChecker, TournamentCheck
from data.pairings.generators import BbpPairingsGenerator


def main(
    n: int,
):
    """Generate *n* tournaments and check them."""
    pairings_checker_dir: Path = TMP_DIR / 'pairings_checker'
    pairings_checker_dir.mkdir(exist_ok=True, parents=True)
    tournament_checks: list[TournamentCheck] = []
    for i in range(1, max(n, 1) + 1):
        tournament_file: Path = pairings_checker_dir / f'{i:05d}.trfx'
        if BbpPairingsGenerator().generate_tournament(
            tournament_file,
            i,
            cache=True,
        ):
            tournament_checks.append(
                BbpPairingsChecker.check_tournament(
                    tournament_file,
                    cache=True,
                )
            )
    print_interactive_info('Internal FPC (Free Pairing Checker)')
    bbp_pairings_installer = BbpPairingsInstaller()
    print_interactive_info(
        f'- Reference RTG: {bbp_pairings_installer.name} v{bbp_pairings_installer.version}'
    )
    print_interactive_info(f'- Number of test tournaments: {len(tournament_checks)}')
    print_interactive_info(
        f'- Rounds per test tournament (min/max/avg): {min(tournament_check.rounds for tournament_check in tournament_checks)}/{max(tournament_check.rounds for tournament_check in tournament_checks)}/{sum(tournament_check.rounds for tournament_check in tournament_checks) / len(tournament_checks):.2f}'
    )
    print_interactive_info(
        f'- Number of rounds with pairing differences detected by internal checker: {len([tournament_check for tournament_check in tournament_checks if tournament_check.diff])}'
    )


if __name__ == '__main__':
    main(300)
