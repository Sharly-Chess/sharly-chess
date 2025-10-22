from pathlib import Path

from common import TMP_DIR
from data.pairings.engines import BbpPairings


def main(
    n: int,
):
    """Generate *n* tournaments and check them."""
    bbp_pairings: BbpPairings = BbpPairings()
    pairings_checker_dir: Path = TMP_DIR / 'pairings_checker'
    pairings_checker_dir.mkdir(exist_ok=True, parents=True)
    for i in range(1, max(n, 1) + 1):
        tournament_file: Path = pairings_checker_dir / f'{i:05d}.trf'
        bbp_pairings.generate_tournament(
            tournament_file,
            i,
            overwrite=False,
        )
        bbp_pairings.check_tournament(
            tournament_file,
            overwrite=False,
        )


if __name__ == '__main__':
    main(5000)
