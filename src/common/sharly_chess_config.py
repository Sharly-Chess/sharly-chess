import locale
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, overload, TYPE_CHECKING

import jinja2
import litestar
import uvicorn
from packaging.version import Version

from common import (
    BASE_DIR,
    EVENTS_DIR,
    SHARLY_CHESS_VERSION,
    TEST_ENV,
    enable_experimental_features,
)
from common.i18n import (
    DEFAULT_LOCALE,
    _,
    locales,
    normalize_bcp47_to_locale,
    read_macos_global_prefs,
    set_locale,
)
from common.logger import set_logging_config, get_logger
from common.network import find_lan_interfaces, LOCALHOST_IP
from common.singleton import Singleton
from plugins.manager import plugin_manager
from utils.enum import Result
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.config.config_store import StoredConfig

if TYPE_CHECKING:
    from data.player import Federation

logger: logging.Logger = get_logger()


class SharlyChessConfig(metaclass=Singleton):
    """The configuration for the application, read from the database."""

    def __init__(self):
        self.web_port: int | None = None
        self._stored_config: StoredConfig | None = None

    @staticmethod
    def _get_system_user_locale() -> str | None:
        """Returns the locale used by the user at system-level,
        if known by the i18n stuff (otherwise returns None)."""
        if TEST_ENV:
            return 'en_GB'
        if sys.platform == 'win32':  # pragma: py-not-win32
            import ctypes

            windll = ctypes.windll.kernel32
            try:
                # Locale ID → Windows locale name → Python locale key
                # locale.windows_locale maps LCIDs to names like 'en_GB'
                system_user_locale = locale.windows_locale[
                    windll.GetUserDefaultUILanguage()
                ]
                logger.info('User locale (Windows): %s', system_user_locale)
                return system_user_locale
            except Exception as e:
                logger.debug('Failed to get Windows UI language: %s', e)
                # fall through to generic fallback below

        elif sys.platform == 'darwin':
            prefs = read_macos_global_prefs()
            lang_list = prefs.get('AppleLanguages') or []
            apple_locale = prefs.get('AppleLocale')

            if lang_list:
                loc = normalize_bcp47_to_locale(str(lang_list[0]))
                logger.info('User locale (macOS AppleLanguages): %s', loc)
                return loc

            if apple_locale:
                loc = normalize_bcp47_to_locale(str(apple_locale))
                logger.info('User locale (macOS AppleLocale): %s', loc)
                return loc

            # last-ditch: `defaults read -g AppleLanguages`
            try:
                proc = subprocess.run(
                    ['defaults', 'read', '-g', 'AppleLanguages'],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                # Output is Apple’s property list textual representation; pick first token in quotes
                import re

                m = re.search(r'"([^"]+)"', proc.stdout)
                if m:
                    loc = normalize_bcp47_to_locale(m.group(1))
                    logger.info('User locale (macOS defaults fallback): %s', loc)
                    return loc
            except Exception as e:
                logger.debug('macOS defaults fallback failed: %s', e)

        # Linux / other: rely on locale module / env
        try:
            # Ensure LC_CTYPE is initialized from environment
            locale.setlocale(locale.LC_CTYPE, '')
        except Exception:
            pass

        lang = (
            os.environ.get('LC_ALL')
            or os.environ.get('LC_MESSAGES')
            or os.environ.get('LANG')
            or ''
        )

        if lang:
            # LANG often looks like 'en_GB.UTF-8' → strip encoding
            loc = lang.split('.', 1)[0]
            logger.info('User locale (env): %s', loc)
            return loc

        # Final fallback: locale.getlocale()
        try:
            loc_tuple = locale.getlocale()  # (language_code, encoding)
            if loc_tuple and loc_tuple[0]:
                logger.info('User locale (locale.getlocale): %s', loc_tuple[0])
                return loc_tuple[0]
        except Exception:
            pass

        logger.info('User locale: unknown')
        return None

    @staticmethod
    def _get_user_locale(system_user_locale: str | None) -> str:
        """Returns the locale to set in Sharly Chess."""
        if system_user_locale is not None:
            user_locale: str = system_user_locale[:2]
            if user_locale in locales:
                return user_locale
            logger.warning(
                'Unknown locale: %s (%s by default)', user_locale, DEFAULT_LOCALE
            )
        return DEFAULT_LOCALE

    def load_and_set_env(self):
        with ConfigDatabase() as config_database:
            stored_config: StoredConfig = config_database.load_stored_config()
        if not stored_config.locale:
            system_user_locale: str | None = self._get_system_user_locale()
            stored_config.locale = self._get_user_locale(system_user_locale)
            with ConfigDatabase(write=True) as config_database:
                config_database.update_stored_config(stored_config)
        if TEST_ENV:
            stored_config.federation = SharlyChessConfig.tests_federation
        set_locale(stored_config.locale)
        set_logging_config(
            console_log_level=stored_config.console_log_level,
            console_color=stored_config.console_color,
            console_show_date=stored_config.console_show_date,
            console_show_level=stored_config.console_show_level,
        )
        enable_experimental_features(stored_config.experimental)
        plugin_manager.reload_register()
        self._stored_config = stored_config

    @property
    def stored_config(self) -> StoredConfig:
        if not self._stored_config:
            self.load_and_set_env()
            assert self._stored_config is not None
        return self._stored_config

    @property
    def force_edit(self) -> bool:
        return self.stored_config.force_edit and not TEST_ENV

    @property
    def console_log_level(self) -> int:
        return self.stored_config.console_log_level or self.default_console_log_level

    @property
    def console_log_level_str(self) -> str:
        return self.console_log_levels[self.console_log_level]

    @property
    def console_color(self) -> bool:
        return self.stored_config.console_color

    @property
    def console_show_date(self) -> bool:
        return self.stored_config.console_show_date

    @property
    def console_show_level(self) -> bool:
        return self.stored_config.console_show_level

    @property
    def experimental(self) -> bool:
        return self.stored_config.experimental

    @property
    def experimental_features(self) -> list[str]:
        return [
            _(
                'Support for all FIDE recognised tie-break (including ones that are not compatible with Papi)'
            ),
        ]

    @property
    def launch_browser(self) -> bool:
        return self.stored_config.launch_browser and not TEST_ENV

    @property
    def federation(self) -> Optional['Federation']:
        from data.player import Federation

        if self.stored_config.federation is not None:
            return Federation(self.stored_config.federation)
        else:
            return None

    @property
    def locale(self) -> str:
        return self.stored_config.locale or DEFAULT_LOCALE

    # The port used by the Uvicorn web server.
    web_host: str = '0.0.0.0'

    # The ports the web server tries to start on, tried one after the other.
    web_ports: list[int] = (
        [
            80,
            81,
            8080,
            8081,
        ]
        if not TEST_ENV
        else [9000]
    )

    """ The accepted console log levels. """
    console_log_levels: dict[int, str] = {
        logging.DEBUG: 'DEBUG',
        logging.INFO: 'INFO',
        logging.WARNING: 'WARNING',
        logging.ERROR: 'ERROR',
    }

    # The default console log level, used by default.
    default_console_log_level: int = logging.INFO

    default_pairing_variation_id = 'SWISS_STANDARD'

    """ The URL of the project. """
    web_url: str = 'https://sharly-chess.com'

    """ The contact email. """
    mail: str = 'contact@sharly-chess.com'

    version = SHARLY_CHESS_VERSION

    en_copyright: str = '© Sharly Chess project 2013-2025'

    @property
    def copyright(self) -> str:
        """The copyright of the application."""
        return f'© {self.project} 2013-2025'

    @property
    def project(self) -> str:
        """The project of the application."""
        return _('Sharly Chess project')

    # The extension of event databases (Sharly Chess Event).
    event_database_ext: str = 'sce'

    # The old extension of event databases (used to recover data from previous releases).
    event_database_old_ext: str = 'db'

    event_archive_base_path = EVENTS_DIR / 'archives'

    # The extension of archives event databases (Sharly Chess Archive).
    event_archive_ext: str = 'sca'

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

    # The path to raw SQL files.
    database_sql_path: Path = BASE_DIR / 'src' / 'database' / 'sql'

    # The path of the files used to generate example event databases.
    example_events_path = BASE_DIR / 'example_events'

    uniq_id_regex = re.compile(r'^[0-9a-zA-Z_\-]+$')

    # The versions of the libraries for which the version can be easily extracted.
    litestar_version: Version = Version(litestar.__version__.formatted(short=True))
    jinja2_version: Version = Version(jinja2.__version__)
    uvicorn_version: Version = Version(uvicorn.__version__)

    # Other library versions, set manually and checked.
    bootstrap_version: Version = Version('5.3.3')
    bootstrap_icons_version: Version = Version('1.11.3')
    htmx_version: Version = Version('2.0.4')
    htmx_remove_me_version: Version = Version('2.0.0')
    htmx_multi_swap_version: Version = Version('2.0.0')
    htmx_ws_version: Version = Version('2.0.3')
    jquery_version: Version = Version('3.7.1')
    sortable_version: Version = Version('1.15.6')
    jstree_version: Version = Version('3.3.17')
    morphdom_version: Version = Version('2.7.4')
    select2_version: Version = Version('4.0.13')
    select2_bootstrap_theme_version: Version = Version('1.3.0')

    @overload
    def app_url(self, ip: str) -> str: ...

    @overload
    def app_url(self, ip: None) -> None: ...

    def app_url(self, ip: str | None) -> str | None:
        """Returns the URL of the application for the given IP."""
        if ip is None:
            return None
        return f'http://{ip}{f":{self.web_port}" if self.web_port != 80 else ""}'

    @property
    def lan_ifaces(self) -> list[dict[str, str]]:
        """[{ip, iface, type, label}]"""
        try:
            data = find_lan_interfaces()
            logger.debug('LAN ifaces: %s', data)
            return data
        except Exception as e:
            logger.debug('find_lan_interfaces failed: %s', e)
            return []

    @property
    def lan_ips(self) -> list[str]:
        return [d['ip'] for d in self.lan_ifaces]

    @property
    def local_ip(self) -> str:
        """Returns the local IP (localhost) of the server (with arbiter access)."""
        return LOCALHOST_IP

    @property
    def lan_urls(self) -> list[str]:
        return [self.app_url(ip_info['ip']) for ip_info in self.lan_ifaces]

    @property
    def local_url(self) -> str:
        """The local URL of the application (with arbiter access)."""
        return self.app_url(self.local_ip)

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

    # True to show the players' opponent on players screens (may be changed for each screen).
    default_players_show_opponent: bool = True

    # The default delay between pages on rotators (in seconds).
    default_rotator_delay: int = 1 if TEST_ENV else 15

    @property
    def default_timer_round_text_before(self) -> str:
        """Returns the default text shown on timers before the start of a round."""
        return _('Start of round {} in %s')

    @property
    def default_timer_round_text_after(self) -> str:
        """Returns the default text shown on timers after the start of a round."""
        return _('Round {} started for %s')

    # The delay before checking if the user index page has changed.
    user_index_update_delay: int = 1 if TEST_ENV else 10

    # The delay before checking if a user event page has changed.
    user_event_update_delay: int = 1 if TEST_ENV else 10

    # The delay before checking if a user screen page has changed.
    user_screen_update_delay: int = 1 if TEST_ENV else 10

    # The numbers of columns allowed on pages with grids.
    allowed_columns: list[int] = [1, 2, 3, 4, 6]

    # The default number of columns.
    default_columns: int = 4

    # The error background image.
    error_background_image: str = '/static/images/sharly-chess-error.png'

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
    default_paired_bye_result: Result = Result.WIN

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

    default_prize_currency = 'EUR'

    # The test federation, used not to need to set the federation when entering the application
    tests_federation: str = 'FID'

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
