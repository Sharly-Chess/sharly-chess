import logging
import platform
import re
import socket
from datetime import datetime
from logging import Logger
from pathlib import Path

import jinja2
import litestar
import pyodbc
import uvicorn
from packaging.version import Version

from common import TMP_DIR, BASE_DIR, DEVEL_ENV, EXPERIMENTAL_FEATURES_ENV_VAR
from common.config_reader import ConfigReader
from common.i18n import (
    set_locale,
    default_locale,
    _,
    locale_localized_name,
    trusted_locales,
)
from common.logger import (
    get_logger,
    configure_logger,
    print_interactive_error,
    print_interactive_input,
    input_interactive,
    print_interactive_info,
    print_interactive_success,
)
from common.singleton import Singleton
from data.util import Result

logger: Logger = get_logger()


class PapiWebConfig(metaclass=Singleton):
    """The configuration for the application.
    Only 5 properties can be configured:
        1. The logging level
        2. The web host IP
        3. The web port
        4. Whether a browser window opens
        5. The delay between FFE uploads."""

    """ The configuration file. """
    config_file: Path = Path('papi-web.ini')

    """ The default values of the configuration file values (if not set on the configuration file). """
    _default_log_level: int = logging.INFO
    _default_web_host: str = '0.0.0.0'
    _default_web_port: int = 80
    _default_web_launch_browser: bool = True
    _default_ffe_upload_delay: int = 180

    """ The minimum delay between two upload to the FFE website. """
    min_ffe_upload_delay: int = 60

    """ The accepted log levels. """
    log_levels: dict[int, str] = {
        logging.DEBUG: 'DEBUG',
        logging.INFO: 'INFO',
        logging.WARNING: 'WARNING',
        logging.ERROR: 'ERROR',
    }

    def __init__(self):
        if not default_locale:
            # This happens only for developers when no MO files are available
            raise FileNotFoundError('No MO files found, please run i18n_update.')
        self._log_level: int | None = None
        self._web_host: str | None = None
        self._web_port: int | None = None
        self._web_launch_browser: bool | None = None
        self._ffe_upload_delay: int | None = None
        self.locales: list[str] = trusted_locales
        self.locale: str | None = None
        self._local_ip: str | None = None
        self._lan_ip: str | None = None
        self.reader = ConfigReader(self.config_file)
        if not self.reader.errors and not self.reader.warnings:
            section_key = 'i18n'
            try:
                options = self.reader[section_key]
                key = 'experimental_locales'
                if key in options and DEVEL_ENV:
                    self.reader.add_warning(
                        _(
                            'Option is obsolete, set environment variable [{var}=1] instead.'
                        ).format(var=EXPERIMENTAL_FEATURES_ENV_VAR),
                        section_key,
                        key,
                    )
                key = 'locale'
                try:
                    locale = options[key]
                    if locale in self.locales:
                        self.locale = locale
                    else:
                        self.reader.add_warning(
                            _('Locale [{locale}] not found.').format(locale=locale),
                            section_key,
                            key,
                        )
                except (TypeError, KeyError):
                    self.reader.add_warning(_('Option not set.'), section_key, key)
            except KeyError:
                self.reader.add_warning(_('Section not found.'), section_key)
            if self.locale:
                set_locale(self.locale)
            else:
                set_locale(default_locale)
                print_interactive_input(_('The following languages are available:'))
                locale_range = range(1, len(self.locales) + 1)
                for num in locale_range:
                    locale: str = self.locales[num - 1]
                    print_interactive_input(
                        f'  - [{num}] {locale} ({locale_localized_name(locale)})'
                    )
                locale_num: int | None = None
                while locale_num is None:
                    choice: str = input_interactive(_('Your choice: '))
                    try:
                        locale_num = int(choice)
                        if locale_num not in locale_range:
                            locale_num = None
                    except ValueError:
                        pass
                self.locale = self.locales[locale_num - 1]
                set_locale(self.locale)
                self.save_locale_preference()
            # Once the language is set, make sure that important directories can be used
            try:
                PapiWebConfig.event_path.mkdir(parents=True, exist_ok=True)
            except PermissionError as pe:
                logger.critical(
                    f'Could not create directory [{TMP_DIR.absolute()}]: {pe}'
                )
                raise pe
            logger.debug('ODBC drivers found:')
            for driver in pyodbc.drivers():
                logger.debug(f' - {driver}')
            logger.debug('System information:')
            logger.debug(
                f' - Machine/processor: {platform.machine()}/{platform.processor()}'
            )
            logger.debug(f' - Platform: {platform.platform()}')
            logger.debug(f' - Architecture: {" ".join(platform.architecture())}')
            section_key = 'logging'
            try:
                options = self.reader[section_key]
                key = 'level'
                try:
                    level = options[key]
                    try:
                        self._log_level = [
                            k for k, v in self.log_levels.items() if v == level
                        ][0]
                    except IndexError:
                        self.reader.add_warning(
                            _(
                                'Invalid log level [{level}], by default [{default}].'
                            ).format(
                                level=level,
                                default=self.log_levels[self._default_log_level],
                            ),
                            section_key,
                            key,
                        )
                except (TypeError, KeyError):
                    self.reader.add_warning(
                        _('Option not set, by default [{default}].').format(
                            default=self.log_levels[self._default_log_level]
                        ),
                        section_key,
                        key,
                    )
            except KeyError:
                self.reader.add_warning(_('Section not found.'), section_key)
            section_key = 'web'
            if section_key not in self.reader:
                self.reader.add_warning(_('Section not found.'), section_key)
            else:
                web_section = self.reader[section_key]
                key = 'host'
                if key not in web_section:
                    self.reader.add_warning(_('Option not set.'), section_key, key)
                else:
                    self._web_host = self.reader.get(section_key, key)
                    matches = re.match(r'^(\d+)\.(\d+)\.(\d+)\.(\d+)$', self._web_host)
                    if matches:
                        for i in range(4):
                            if int(matches.group(i + 1)) > 255:
                                self._web_host = None
                    else:
                        self._web_host = None
                    if self.web_host is None:
                        self.reader.add_warning(
                            _(
                                'Invalid host configuration [{host}], by default [{default}].'
                            ).format(
                                host=self.reader.get(section_key, key),
                                default=self._default_web_host,
                            ),
                            section_key,
                            key,
                        )
                key = 'port'
                if key not in web_section:
                    self.reader.add_warning(
                        _('Option not set, by default [{default}].').format(
                            default=self._default_web_port
                        ),
                        section_key,
                        key,
                    )
                else:
                    self._web_port = self.reader.getint_safe(section_key, key)
                    if self.web_port is None:
                        self.reader.add_warning(
                            _('Invalid port [{port}], by default [{default}].').format(
                                port=self.reader.get(section_key, key),
                                default=self._default_web_port,
                            ),
                            section_key,
                            key,
                        )
                key = 'launch_browser'
                if key not in web_section:
                    self.reader.add_warning(
                        _('Option not set, by default [{default}].').format(
                            default='on' if self._default_web_launch_browser else 'off'
                        ),
                        section_key,
                        key,
                    )
                else:
                    self._web_launch_browser = self.reader.getboolean_safe(
                        section_key, key
                    )
                    if self._web_launch_browser is None:
                        self.reader.add_error(
                            _('Invalid value [{value}].').format(
                                value=self.reader.get(section_key, key)
                            ),
                            section_key,
                            key,
                        )
            section_key = 'ffe'
            try:
                options = self.reader[section_key]
                key = 'upload_delay'
                if key not in options:
                    self.reader.add_warning(
                        _('Option not set, by default [{default}].').format(
                            ffe_upload_delay=self._default_ffe_upload_delay
                        ),
                        section_key,
                        key,
                    )
                else:
                    self._ffe_upload_delay = self.reader.getint_safe(section_key, key)
                    if (
                        self.ffe_upload_delay is None
                        or self.ffe_upload_delay < self.min_ffe_upload_delay
                    ):
                        self.reader.add_warning(
                            _('Invalid delay [{delay}], by default [{default}]').format(
                                delay=self.reader.get(section_key, key),
                                default=self._default_ffe_upload_delay,
                            ),
                            section_key,
                            key,
                        )
            except KeyError:
                self.reader.add_warning(
                    _('Section not found, default configuration set.'), section_key
                )
        else:
            self.reader.add_debug('Default configuration set.')
        configure_logger(self.log_level)

    def save_locale_preference(self):
        config_save: Path = (
            self.config_file.parent
            / f'{self.config_file.name}.{datetime.now().strftime("%Y-%m-%d-%H-%M-%S")}'
        )
        try:
            self.config_file.rename(config_save)
            print_interactive_info(
                _('Your file {ini_file} has been saved as {ini_file_org}.').format(
                    ini_file=self.config_file, ini_file_org=config_save
                )
            )
        except Exception as ex:
            print_interactive_error(
                _('Could not save {ini_file} to {ini_file_org}: {ex}.').format(
                    ini_file=self.config_file, ini_file_org=config_save, ex=ex
                )
            )
            return
        try:
            with open(config_save, 'r') as input_file:
                with open(self.config_file, 'w', encoding='utf-8') as output_file:
                    print_interactive_info(
                        _('Adding lines to {file}...').format(file=self.config_file)
                    )
                    for line in [
                        _('[i18n] # Added by Papi-web {version}').format(
                            version=PapiWebConfig.version
                        ),
                        f'locale = {self.locale}',
                        '',
                    ]:
                        output_file.write(f'{line}\n')
                        if line:
                            print_interactive_info(f'- {line}')
                    locale_pattern = re.compile(r'^locale\s*=')
                    for line in input_file:
                        if line.startswith('[i18n]') or locale_pattern.match(line):
                            output_file.write(
                                _(
                                    '# The line below has been commented by Papi-web {version}'
                                ).format(version=PapiWebConfig.version)
                            )
                            output_file.write(f'\n# {line}')
                        else:
                            output_file.write(line)
            print_interactive_success(
                _('Your file {ini_file} has been modified.').format(
                    ini_file=self.config_file
                )
            )
        except Exception as ex:
            print_interactive_error(
                _('Could not write to {ini_file}: {ex}.').format(
                    ini_file=self.config_file, ex=ex
                )
            )

    @property
    def log_level(self) -> int:
        return self._log_level or self._default_log_level

    @property
    def log_level_str(self) -> str:
        return self.log_levels[self.log_level]

    @property
    def web_host(self) -> str:
        return self._web_host or self._default_web_host

    @property
    def web_port(self) -> int:
        return self._web_port or self._default_web_port

    @property
    def web_launch_browser(self) -> bool:
        return (
            self._web_launch_browser
            if self._web_launch_browser is not None
            else self._default_web_launch_browser
        )

    @property
    def ffe_upload_delay(self) -> int:
        return self._ffe_upload_delay or self._default_ffe_upload_delay

    """ The version of the application. """
    version: Version = Version('2.4.23')

    """ The URL of the project. """
    url: str = 'https://github.com/papi-web-org/papi-web'

    """ The contact email. """
    mail: str = 'papi-web@echecs-bretagne.fr'

    @property
    def copyright(self) -> str:
        """The copyright of the application."""
        return f'© {self.project} 2013-2025'

    @property
    def project(self) -> str:
        """The project of the application."""
        return _('Papi-web project')

    """ The path where event databases are stored. """
    event_path: Path = Path() / 'events'

    """ The extension of event databases. """
    event_database_ext: str = 'db'

    """ The extension of archives event databases. """
    event_archive_ext: str = 'arch'

    """ The base path where event database backups are stored. """
    event_backup_base_path: Path = event_path / 'backups'

    """ The extension of backup event databases. """
    event_backup_ext: str = 'backup'

    """ The extension of federation databases. """
    federation_database_ext: str = 'db'

    """ The path to the user custom files. """
    custom_path: Path = Path().absolute() / 'custom'

    """ The path to the embedded custom files. """
    embedded_custom_path: Path = BASE_DIR / 'src/custom'

    """ The default path to the Papi files. """
    default_papi_path: Path = Path() / 'papi'

    """ The extension of Papi files. """
    papi_ext: str = 'papi'

    """ The path to database source files (see below). """
    _database_path: Path = BASE_DIR / 'src/database'

    """ The path to SQL files (used to create new event databases). """
    database_sql_path: Path = _database_path / 'sql'

    """ The path to YAML files (used to create example databases). """
    database_yml_path: Path = _database_path / 'yml'

    """ The extension of YAML files. """
    yml_ext: str = 'yml'

    """ The versions of the libraries for which the version can be easily extracted. """
    litestar_version: Version = litestar.__version__.formatted(short=True)
    jinja2_version: Version = jinja2.__version__
    uvicorn_version: Version = uvicorn.__version__
    pyodbc_version: Version = Version(pyodbc.version)

    """ Other library versions, set manually and checked. """
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
        if self._lan_ip is None:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0)
            try:
                s.connect(('10.254.254.254', 1))  # doesn't even have to be reachable
                self._lan_ip = s.getsockname()[0]
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            finally:
                s.close()
        return self._lan_ip

    @property
    def local_ip(self) -> str:
        """Returns the local IP (localhost) of the server (with arbiter access)."""
        if self._local_ip is None:
            self._local_ip = '127.0.0.1'
        return self._local_ip

    @property
    def lan_url(self) -> str:
        """The URL of the application on the LAN/WAN."""
        return self._url(self.lan_ip)

    @property
    def local_url(self) -> str:
        """The local URL of the application (with arbiter access)."""
        return self._url(self.local_ip)

    """ The default number of illegal moves to record. """
    default_record_illegal_moves_number: int = 0

    """ The default colors for the timers. """
    default_timer_colors: dict[int, str] = {
        1: '#00FF00',
        2: '#FF7700',
        3: '#FF0000',
    }

    """ The default delays for the timers. """
    default_timer_delays: dict[int, int] = {
        1: 15,
        2: 5,
        3: 10,
    }

    """ The default text colour for the alert messages. """
    default_message_color: str = '#FF0000'

    """ The default background colour for the alert messages. """
    default_message_background_color: str = '#FFFF00'

    """ True to show an exit button on input screens by default (may be changed for each screen). """
    default_input_exit_button: bool = True

    """ True to show unpaired players on players screens (may be changed for each screen). """
    default_players_show_unpaired: bool = True

    """ The default delay between pages on rotators (in seconds). """
    default_rotator_delay: int = 15

    """ The default text shown on timers before the start of a round. """
    default_timer_round_text_before: str = 'Début de la ronde {} dans %s'

    """ The default text shown on timers after the start of a round. """
    default_timer_round_text_after: str = 'Ronde {} commencée depuis %s'

    """ The delay before checking if the user index page has changed. """
    user_index_update_delay: int = 10

    """ The delay before checking if a user event page has changed. """
    user_event_update_delay: int = 10

    """ The delay before checking if a user screen page has changed. """
    user_screen_update_delay: int = 10

    """ The numbers of columns allowed on pages with grids. """
    allowed_columns: list[int] = [1, 2, 3, 4, 6]

    """ The default number of columns. """
    default_columns: int = 4

    """ True to hide the background images by default. """
    default_hide_background_image: bool = False

    """ The default event background image. """
    default_background_image: str = ''

    """ The error background image. """
    error_background_image: str = '/static/images/papi-web-error.png'

    """ The default event background colour. """
    default_background_color: str = '#ffffff'

    """ The default background colour for arbiter pages. """
    admin_background_color: str = ''

    """ The default background colour for user pages. """
    user_background_color: str = default_background_color

    """ The maximum number of results shown on results screens (0 = no limit). """
    default_results_screen_limit: int = 0

    """ The age of the oldest results shown on results screens (in minutes). """
    default_results_screen_max_age: int = 60

    """ The ChessEvent download URL. """
    chessevent_download_url: str = 'https://chessevent.echecs-bretagne.fr/download'

    """ The default first board number for tournaments. """
    default_first_board_number: int = 1

    """ The points scored by players paired bye. """
    default_paired_bye_points: Result = Result.GAIN

    """ The default maximum number of byes for a player in a tournament. """
    default_max_byes: int = 1

    """ The default last rounds of tournaments where byes are not allowed anymore. """
    default_last_rounds_no_byes: int = 3

    """ The default filter for the players columns. """
    default_players_filter_columns: list[str] = [
        'federation',
        'league',
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
        'history',
    ]

    """ The federation names. """
    federations: dict[str, str] = {
        'NON': 'None',
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
    }

    """ The FFE league names. """
    ffe_leagues: dict[str, str] = {
        '': '',
        'ARA': 'Auvergne-Rhône-Alpes',
        'BFC': 'Bourgogne-Franche-Comté',
        'BRE': 'Bretagne',
        'CRS': 'Corse',
        'CVL': 'Centre-Val de Loire',
        'EST': 'Grand-Est',
        'GUA': 'Guadeloupe',
        'GUY': 'Guyane',
        'HDF': 'Hauts-de-France',
        'IDF': 'Île-de-France',
        'MAR': 'Martinique',
        'NAQ': 'Nouvelle-Aquitaine',
        'NCA': 'Nouvelle-Calédonie',
        'NOR': 'Normandie',
        'OCC': 'Occitanie',
        'PAC': "Provence-Alpes-Côte d'azur",
        'PDL': 'Pays de la Loire',
        'POL': 'Saint-Pierre-et-Miquelon',
        'REU': 'Réunion',
    }
