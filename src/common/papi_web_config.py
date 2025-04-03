import logging
import platform
import socket
from logging import Logger
from pathlib import Path

import jinja2
import litestar
import pyodbc
import uvicorn
from packaging.version import Version

from common import BASE_DIR, EXPERIMENTAL_FEATURES, EVENTS_DIR, PAPI_WEB_VERSION
from common.i18n import (
    DEFAULT_LOCALE,
    _, trusted_locales, untrusted_locales, set_locale,
)
from common.logger import (
    get_logger,
    configure_logger,
)
from common.singleton import Singleton
from data.player import Federation
from data.util import Result
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.config.config_store import StoredConfig

logger: Logger = get_logger()


class PapiWebConfig(metaclass=Singleton):
    """The configuration for the application, read from the database.
    Only 5 properties can be configured:
        1. The logging level
        2. The web host IP
        3. The web port
        4. Whether a browser window opens
        5. The delay between FFE uploads."""

    # The default log level, used by default.
    default_log_level: int = logging.INFO

    # The port ued by the Uvicorn web server.
    web_host: str = '0.0.0.0'

    # The ports the web server tries to start on, tried one after the other.
    web_ports: list[int] = [80, 81, 8080, 8081, ]

    # The default behaviour to open a browser after the startup of the web server.
    default_launch_browser: bool = True

    """ The accepted log levels. """
    log_levels: dict[int, str] = {
        logging.DEBUG: 'DEBUG',
        logging.INFO: 'INFO',
        logging.WARNING: 'WARNING',
        logging.ERROR: 'ERROR',
    }

    def __init__(self):
        if not DEFAULT_LOCALE:
            # This happens only for developers when no MO files are available
            raise FileNotFoundError('No MO files found, please run i18n_update.')
        self.web_port: int | None = None
        self.locales: list[str] = trusted_locales
        if EXPERIMENTAL_FEATURES:
            self.locales += untrusted_locales
        self.stored_config: StoredConfig = self.load()
        set_locale(self.locale)
        logger.debug('ODBC drivers found:')
        for driver in pyodbc.drivers():
            logger.debug(' - %s', driver)
        logger.debug('System information:')
        logger.debug(
            ' - Machine/processor: %s/%s',
            platform.machine(), platform.processor()
        )
        logger.debug(' - Platform: %s', platform.platform())
        logger.debug(' - Architecture: %s', " ".join(platform.architecture()))
        configure_logger(self.log_level)

    def reload(self):
        self.stored_config = self.load()

    @staticmethod
    def load() -> StoredConfig:
        with ConfigDatabase() as config_database:
            return config_database.load_stored_config()

    @property
    def force_edit(self) -> bool:
        return self.stored_config.force_edit

    @property
    def log_level(self) -> int:
        return self.stored_config.log_level or self.default_log_level

    @property
    def log_level_str(self) -> str:
        return self.log_levels[self.log_level]

    @property
    def launch_browser(self) -> bool:
        if self.stored_config.launch_browser is not None:
            return self.stored_config.launch_browser
        else:
            return self.default_launch_browser

    @property
    def federation(self) -> Federation:
        return Federation(self.stored_config.federation or self.default_federation)

    @property
    def locale(self) -> str:
        return self.stored_config.locale or DEFAULT_LOCALE

    # The delay between two uploads to the FFE website.
    # TODO move this to the ffe plugin
    ffe_upload_delay: int = 180

    """ The URL of the project. """
    url: str = 'https://github.com/papi-web-org/papi-web'

    """ The contact email. """
    mail: str = 'papi-web@echecs-bretagne.fr'

    version = PAPI_WEB_VERSION

    @property
    def copyright(self) -> str:
        """The copyright of the application."""
        return f'© {self.project} 2013-2025'

    @property
    def project(self) -> str:
        """The project of the application."""
        return _('Papi-web project')

    # The extension of event databases.
    event_database_ext: str = 'db'

    # The extension of archives event databases.
    event_archive_ext: str = 'arch'

    # The base path where event database backups are stored.
    event_backup_base_path: Path = EVENTS_DIR / 'backups'

    # The extension of backup event databases.
    event_backup_ext: str = 'backup'

    # The extension of federation databases.
    federation_database_ext: str = 'db'

    # The name of the folder for the custom files, used to
    # recover custom files from previously installed releases.
    custom_folder: str = 'custom'

    # The path to the user custom files.
    custom_path: Path = Path().absolute() / custom_folder

    # The path to the embedded custom files.
    embedded_custom_path: Path = BASE_DIR / 'src' / custom_folder

    # The name of the default folder for the Papi files,
    # used to recover Papi files from previous releases.
    default_papi_folder: str = 'papi'

    # The default path to the Papi files.
    default_papi_path: Path = Path() / default_papi_folder

    # The extension of Papi files.
    papi_ext: str = 'papi'

    # The path to database source files (see below).
    _database_path: Path = BASE_DIR / 'src/database'

    # The path to SQL files (used to create new event databases).
    database_sql_path: Path = _database_path / 'sql'

    # The path to YAML files (used to create example databases).
    database_yml_path: Path = _database_path / 'yml'

    # The extension of YAML files.
    yml_ext: str = 'yml'

    # The versions of the libraries for which the version can be easily extracted.
    litestar_version: Version = litestar.__version__.formatted(short=True)
    jinja2_version: Version = jinja2.__version__
    uvicorn_version: Version = uvicorn.__version__
    pyodbc_version: Version = Version(pyodbc.version)

    # Other library versions, set manually and checked.
    bootstrap_version: Version = Version('5.3.3')
    assert (
        BASE_DIR / f'src/web/static/lib/bootstrap/bootstrap-{bootstrap_version}-dist'
    ).is_dir()
    bootstrap_icons_version: Version = Version('1.11.3')
    assert (
        BASE_DIR
        / f'src/web/static/lib/bootstrap-icons/bootstrap-icons-{bootstrap_icons_version}'
    ).is_dir()
    htmx_version: Version = Version('1.9.12')
    assert (BASE_DIR / f'src/web/static/lib/htmx/htmx-{htmx_version}').is_dir()
    jquery_version: Version = Version('3.7.1')
    assert (
        BASE_DIR / f'src/web/static/lib/jquery/jquery-{jquery_version}.min.js'
    ).is_file()
    sortable_version: Version = Version('1.15.2')
    assert (
        BASE_DIR / f'src/web/static/lib/sortable/sortable-{sortable_version}'
    ).is_dir()
    jstree_version: Version = Version('3.3.17')
    assert (
        BASE_DIR / f'src/web/static/lib/jstree/jstree-{jstree_version}-dist'
    ).is_dir()

    def _url(self, ip: str | None) -> str | None:
        """Returns the URL of the application for the given IP."""
        if ip is None:
            return None
        return f'http://{ip}{f":{self.web_port}" if self.web_port != 80 else ""}'

    @property
    def lan_ip(self) -> str | None:
        """Returns the IP of the server on the LAN/WAN."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            s.connect(('10.254.254.254', 1))  # doesn't even have to be reachable
            return s.getsockname()[0]
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        finally:
            s.close()
        return None

    @property
    def local_ip(self) -> str:
        """Returns the local IP (localhost) of the server (with arbiter access)."""
        return '127.0.0.1'

    @property
    def lan_url(self) -> str:
        """The URL of the application on the LAN/WAN."""
        return self._url(self.lan_ip)

    @property
    def local_url(self) -> str:
        """The local URL of the application (with arbiter access)."""
        return self._url(self.local_ip)

    # The default number of illegal moves to record.
    default_record_illegal_moves_number: int = 0

    # The default colors for the timers.
    default_timer_colors: dict[int, str] = {
        1: '#00FF00',
        2: '#FF7700',
        3: '#FF0000',
    }

    # The default delays for the timers.
    default_timer_delays: dict[int, int] = {
        1: 15,
        2: 5,
        3: 10,
    }

    # The default text colour for the alert messages.
    default_message_color: str = '#FF0000'

    # The default background colour for the alert messages.
    default_message_background_color: str = '#FFFF00'

    # True to show an exit button on input screens by default (may be changed for each screen).
    default_input_exit_button: bool = True

    # True to show unpaired players on players screens (may be changed for each screen).
    default_players_show_unpaired: bool = True

    # The default delay between pages on rotators (in seconds).
    default_rotator_delay: int = 15

    # The default text shown on timers before the start of a round.
    default_timer_round_text_before: str = 'Début de la ronde {} dans %s'

    # The default text shown on timers after the start of a round.
    default_timer_round_text_after: str = 'Ronde {} commencée depuis %s'

    # The delay before checking if the user index page has changed.
    user_index_update_delay: int = 10

    # The delay before checking if a user event page has changed.
    user_event_update_delay: int = 10

    # The delay before checking if a user screen page has changed.
    user_screen_update_delay: int = 10

    # The numbers of columns allowed on pages with grids.
    allowed_columns: list[int] = [1, 2, 3, 4, 6]

    # The default number of columns.
    default_columns: int = 4

    # True to hide the background images by default.
    default_hide_background_image: bool = False

    # The default event background image.
    default_background_image: str = ''

    # The error background image.
    error_background_image: str = '/static/images/papi-web-error.png'

    # The default event background colour.
    default_background_color: str = '#ffffff'

    # The default background colour for arbiter pages.
    admin_background_color: str = ''

    # The default background colour for user pages.
    user_background_color: str = default_background_color

    # The maximum number of results shown on results screens (0 = no limit).
    default_results_screen_limit: int = 0

    # The age of the oldest results shown on results screens (in minutes).
    default_results_screen_max_age: int = 60

    # The default first board number for tournaments.
    default_first_board_number: int = 1

    # The default result for players paired bye.
    default_paired_bye_result: Result = Result.GAIN

    # The default maximum number of byes for a player in a tournament.
    default_max_byes: int = 1

    # The default last rounds of tournaments where byes are not allowed anymore.
    default_last_rounds_no_byes: int = 3

    # The default filter for the players columns.
    default_players_filter_columns: list[str] = [
        'federation',
        'club',
        'yob',
        'category',
        'mail',
        'phone',
        'gender',
        'fixed',
        'fide',
        'ffe',
        'check_in',
        'tournament',
        'record',
    ]

    # The default fédération when creating events or players
    default_federation: str = 'FID'

    # The federation names.
    federations: dict[str, str] = {
        'AFG': 'Afghanistan',
        'ALB': 'Albania',
        'ALG': 'Algeria',
        'AND': 'Andorra',
        'ANG': 'Angola',
        'ANT': 'Antigua and Barbuda',
        'ARG': 'Argentina',
        'ARM': 'Armenia',
        'ARU': 'Aruba',
        'AUS': 'Australia',
        'AUT': 'Austria',
        'AZE': 'Azerbaijan',
        'BAH': 'Bahamas',
        'BRN': 'Bahrain',
        'BAN': 'Bangladesh',
        'BAR': 'Barbados',
        'BLR': 'Belarus',
        'BEL': 'Belgium',
        'BIZ': 'Belize',
        'BER': 'Bermuda',
        'BHU': 'Bhutan',
        'BOL': 'Bolivia',
        'BIH': 'Bosnia & Herzegovina',
        'BOT': 'Botswana',
        'BRA': 'Brazil',
        'BRU': 'Brunei Darussalam',
        'BUL': 'Bulgaria',
        'BUR': 'Burkina Faso',
        'BDI': 'Burundi',
        'CAM': 'Cambodia',
        'CMR': 'Cameroon',
        'CAN': 'Canada',
        'CPV': 'Cape Verde',
        'CAY': 'Cayman Islands',
        'CAF': 'Central African Republic',
        'CHA': 'Chad',
        'CHI': 'Chile',
        'CHN': 'China',
        'CGO': 'Congo',
        'COL': 'Colombia',
        'COM': 'Comoros Islands',
        'CRC': 'Costa Rica',
        'CIV': 'Cote d’Ivoire',
        'CRO': 'Croatia',
        'CUB': 'Cuba',
        'CYP': 'Cyprus',
        'CZE': 'Czech Republic',
        'COD': 'Democratic Republic of the Congo',
        'DEN': 'Denmark',
        'DJI': 'Djibouti',
        'DMA': 'Dominica',
        'DOM': 'Dominican Republic',
        'ECU': 'Ecuador',
        'EGY': 'Egypt',
        'ESA': 'El Salvador',
        'ENG': 'England',
        'GEQ': 'Equatorial Guinea',
        'ERI': 'Eritrea',
        'EST': 'Estonia',
        'SWZ': 'Eswatini',
        'ETH': 'Ethiopia',
        'FAI': 'Faroe Islands',
        'FID': 'International Chess Federation',
        'FIJ': 'Fiji',
        'FIN': 'Finland',
        'FRA': 'France',
        'GAB': 'Gabon',
        'GAM': 'Gambia',
        'GEO': 'Georgia',
        'GER': 'Germany',
        'GHA': 'Ghana',
        'GRE': 'Greece',
        'GRL': 'Groenland',
        'GRN': 'Grenada',
        'GUM': 'Guam',
        'GUA': 'Guatemala',
        'GCI': 'Guernsey',
        'GUY': 'Guyana',
        'HAI': 'Haiti',
        'HON': 'Honduras',
        'HKG': 'Hong Kong, China',
        'HUN': 'Hungary',
        'ISL': 'Iceland',
        'IND': 'India',
        'INA': 'Indonesia',
        'IRI': 'Iran',
        'IRQ': 'Iraq',
        'IRL': 'Ireland',
        'IOM': 'Isle of Man',
        'ISR': 'Israel',
        'ITA': 'Italy',
        'IVB': 'British Virgin Islands',
        'JAM': 'Jamaica',
        'JPN': 'Japan',
        'JCI': 'Jersey',
        'JOR': 'Jordan',
        'KAZ': 'Kazakhstan',
        'KEN': 'Kenya',
        'KOS': 'Kosovo *',
        'KUW': 'Kuwait',
        'KGZ': 'Kyrgyzstan',
        'LAO': 'Laos',
        'LAT': 'Latvia',
        'LBN': 'Lebanon',
        'LES': 'Lesotho',
        'LBR': 'Liberia',
        'LBA': 'Libya',
        'LIE': 'Liechtenstein',
        'LTU': 'Lithuania',
        'LUX': 'Luxembourg',
        'MAC': 'Macau, China',
        'MAD': 'Madagascar',
        'MAW': 'Malawi',
        'MAS': 'Malaysia',
        'MDV': 'Maldives',
        'MLI': 'Mali',
        'MLT': 'Malta',
        'MTN': 'Mauritania',
        'MRI': 'Mauritius',
        'MEX': 'Mexico',
        'MDA': 'Moldova',
        'MNC': 'Monaco',
        'MGL': 'Mongolia',
        'MNE': 'Montenegro',
        'MAR': 'Morocco',
        'MOZ': 'Mozambique',
        'MYA': 'Myanmar',
        'NAM': 'Namibia',
        'NRU': 'Nauru',
        'NEP': 'Nepal',
        'NED': 'Netherlands',
        'AHO': 'Netherlands Antilles',
        'NCL': 'New Caledonia',
        'NZL': 'New Zealand',
        'NCA': 'Nicaragua',
        'NIG': 'Niger',
        'NGR': 'Nigeria',
        'MKD': 'North Macedonia',
        'NOR': 'Norway',
        'OMA': 'Oman',
        'PAK': 'Pakistan',
        'PLW': 'Palau',
        'PLE': 'Palestine',
        'PAN': 'Panama',
        'PNG': 'Papua New Guinea',
        'PAR': 'Paraguay',
        'PER': 'Peru',
        'PHI': 'Philippines',
        'POL': 'Poland',
        'POR': 'Portugal',
        'PUR': 'Puerto Rico',
        'QAT': 'Qatar',
        'ROU': 'Romania',
        'RUS': 'Russia',
        'RWA': 'Rwanda',
        'SKN': 'Saint Kitts and Nevis',
        'LCA': 'Saint Lucia',
        'VIN': 'Saint Vincent and the Grenadines',
        'SMR': 'San Marino',
        'STP': 'Sao Tome and Principe',
        'KSA': 'Saudi Arabia',
        'SCO': 'Scotland',
        'SEN': 'Senegal',
        'SRB': 'Serbia',
        'SEY': 'Seychelles',
        'SLE': 'Sierra Leone',
        'SGP': 'Singapore',
        'SVK': 'Slovakia',
        'SLO': 'Slovenia',
        'SOL': 'Solomon Islands',
        'SOM': 'Somalia',
        'RSA': 'South Africa',
        'KOR': 'South Korea',
        'SSD': 'South Sudan',
        'ESP': 'Spain',
        'SRI': 'Sri Lanka',
        'SUD': 'Sudan',
        'SUR': 'Suriname',
        'SWE': 'Sweden',
        'SUI': 'Switzerland',
        'SYR': 'Syria',
        'TJK': 'Tajikistan',
        'TAN': 'Tanzania',
        'THA': 'Thailand',
        'TLS': 'Timor-Leste',
        'TOG': 'Togo',
        'TGA': 'Tonga',
        'TPE': 'Chinese Taipei',
        'TTO': 'Trinidad & Tobago',
        'TUN': 'Tunisia',
        'TUR': 'Turkiye',
        'TKM': 'Turkmenistan',
        'UGA': 'Uganda',
        'UKR': 'Ukraine',
        'UAE': 'United Arab Emirates',
        'USA': 'United States of America',
        'URU': 'Uruguay',
        'ISV': 'US Virgin Islands',
        'UZB': 'Uzbekistan',
        'VAN': 'Vanuatu',
        'VEN': 'Venezuela',
        'VIE': 'Vietnam',
        'WLS': 'Wales',
        'YEM': 'Yemen',
        'ZAM': 'Zambia',
        'ZIM': 'Zimbabwe',
        'NON': 'None',
    }
