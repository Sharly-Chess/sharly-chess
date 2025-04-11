# Need to import this first to avoid circular imports
import plugins.manager  # noqa
from pairing.bbp_pairings_installer import BbpPairingsInstaller


if __name__ == '__main__':
    BbpPairingsInstaller().install()
