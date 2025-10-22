from pathlib import Path

from common import TMP_DIR
from data.pairings.engines import BbpPairings


def main(
    n: int,
):
    """Generate *n* tournaments and check them."""
    bbp_pairings: BbpPairings = BbpPairings()
    base_dir: Path = TMP_DIR / 'tournament_checker'
    tournaments_dir: Path = base_dir / 'tournaments'
    tournaments_dir.mkdir(exist_ok=True, parents=True)
    check_lists_dir: Path = base_dir / 'check_lists'
    check_lists_dir.mkdir(exist_ok=True, parents=True)
    for i in range(1, max(n, 1) + 1):
        tournament_file: Path = tournaments_dir / f'{i:05d}.trf'
        bbp_pairings.generate_tournament(
            tournament_file,
            i,
            overwrite=False,
        )
        check_list_file: Path = check_lists_dir / f'{i:05d}.list'
        bbp_pairings.check_tournament(
            tournament_file,
            check_list_file,
            overwrite=False,
        )


if __name__ == '__main__':
    main(5000)
