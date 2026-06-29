import re
import shutil
from collections.abc import Collection
from pathlib import Path

from packaging.version import Version, InvalidVersion

from common import (
    EVENTS_DIR,
    CONFIG_FILE,
    ARCHIVES_DIR,
    CUSTOM_DIR,
    DEVEL_ENV,
    DATA_DIR,
    BASE_DIR,
    SHARLY_CHESS_VERSION,
    IS_NEW_INSTALL,
    EXAMPLE_EVENTS_DIR,
)
from common.i18n import _, ngettext
from common.logger import get_logger, input_interactive_yn, input_interactive_choices
from common.sharly_chess_config import SharlyChessConfig
from data.loader import EventLoader
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.local_source_database import LocalSourceDatabaseManager
from plugins.manager import plugin_manager
from utils.enum import Extension

logger = get_logger()


class DataRecovery:
    RECOVERABLE_VERSIONS: list[Version] = []

    @classmethod
    def setup(cls):
        """Setup the Data recovery class. Recovers a version if necessary."""
        path_by_version = cls._get_installed_versions()
        versions = path_by_version.keys()
        is_legacy_install = any(version.major < 5 for version in versions)
        recovered = False
        if IS_NEW_INSTALL and path_by_version:
            if is_legacy_install:
                version = cls._choose_legacy_version_to_recover(path_by_version)
                if version:
                    cls._recover_legacy_version(version, path_by_version[version])
                    recovered = True
            else:
                for version in versions:
                    if version < SHARLY_CHESS_VERSION:
                        cls._recover_version(version, path_by_version[version])
                        recovered = True
                        break

        if DEVEL_ENV and IS_NEW_INSTALL and not recovered:
            if input_interactive_yn(
                title=_('Example databases'),
                question=_('Do you want to install example event databases'),
                yes_is_default=True,
            ):
                for file in EXAMPLE_EVENTS_DIR.glob(f'*.{Extension.EVENT_DB}'):
                    shutil.copy(file, EVENTS_DIR / file.name)

        cls._recover_legacy_event_db()
        cls.RECOVERABLE_VERSIONS = cls.get_recoverable_versions(versions)
        if not is_legacy_install:
            for version in versions:
                if version not in cls.RECOVERABLE_VERSIONS:
                    shutil.rmtree(path_by_version[version])

    @staticmethod
    def _get_installed_versions() -> dict[Version, Path]:
        path_by_version: dict[Version, Path] = {}
        for version_dir in DATA_DIR.glob('*'):
            if not version_dir.is_dir() or not re.match(
                r'^v(\d+\.\d+\.\d+).*$', version_dir.name
            ):
                continue
            try:
                version = Version(version_dir.name[1:])
                if version.major < 5:
                    logger.warning(
                        'version dir [%s] is a legacy version (ignored)',
                        version_dir.absolute(),
                    )
                elif version != SHARLY_CHESS_VERSION:
                    path_by_version[version] = version_dir
            except InvalidVersion:
                logger.warning('invalid version dir [%s]', version_dir.absolute())
        if not path_by_version:
            # If none-legacy data found, skip the legacy recovery
            for version_dir in BASE_DIR.parent.glob('*'):
                if not version_dir.is_dir() or version_dir.samefile(Path('.')):
                    # Only inspect directories not matching the current directory
                    continue
                if matches := re.match(
                    r'^(?:papi-web|sharly-chess)-(\d+\.\d+\.\d+(?:a\d+|b\d+|rc\d+)?)(?:-windows)?$',
                    version_dir.name,
                ):
                    version = Version(matches.group(1))
                else:
                    continue
                if version < Version('2.4.0'):
                    logger.debug('Version [%s] : too old, ignored.', version)
                elif version.major >= 5:
                    logger.debug('Version [%s] : too recent, ignored.', version)
                else:
                    path_by_version[version] = version_dir
        return {
            version: path_by_version[version]
            for version in sorted(path_by_version, reverse=True)
        }

    @classmethod
    def get_recoverable_versions(cls, versions: Collection[Version]) -> list[Version]:
        beta: Version | None = None
        minor: Version | None = None
        patch: Version | None = None
        current = SHARLY_CHESS_VERSION
        recoverable: list[Version] = []
        for version in versions:
            if version >= current:
                continue
            if version.is_prerelease:
                if not beta and not patch:
                    beta = version
                    recoverable.append(version)
                continue
            matches_minor = (version.major, version.minor) == (
                current.major,
                current.minor,
            )
            if not patch and matches_minor:
                patch = version
                recoverable.append(version)
            elif not minor and not matches_minor:
                minor = version
                recoverable.append(version)
        return recoverable

    @classmethod
    def _clean_non_recoverable_data(cls, path_by_version: dict[Version, Path]):
        pass

    @classmethod
    def _recover_version(cls, version: Version, version_dir: Path):
        logger.info('Recovering version [%s]...', version)
        cls._recover_config_file(version_dir / CONFIG_FILE.name)
        for file in (version_dir / EVENTS_DIR.name).glob('*'):
            if not file.is_file():
                continue
            shutil.copy(file, EVENTS_DIR / file.name)
            logger.debug('- Event [%s] recovered', file.stem)

    @classmethod
    def _recover_config_file(cls, old_config_file: Path):
        from gui.server_gui_toga import SharlyChessServerToga

        if not old_config_file.is_file():
            return

        # copy the configuration database to its new destination
        shutil.copy(old_config_file, CONFIG_FILE)
        logger.debug('Configuration file recovered')
        ConfigDatabase.setup()
        config = SharlyChessConfig()
        config.load_and_set_env()
        if SharlyChessServerToga.instance is not None:
            logger.debug('Applying recovered configuration to the Toga app...')
            SharlyChessServerToga.instance.update_from_sharly_chess_config()
        plugin_manager.reload_register()

    # -------------------------------------------------------------------------
    # Legacy
    # -------------------------------------------------------------------------

    @staticmethod
    def _get_legacy_event_files(version_dir: Path) -> list[Path]:
        events_dir = version_dir / EVENTS_DIR.name
        return list(events_dir.glob(f'*.{Extension.EVENT_DB}')) + list(
            events_dir.glob(f'*.{Extension.LEGACY_EVENT_DB}')
        )

    @classmethod
    def _choose_legacy_version_to_recover(
        cls, path_by_version: dict[Version, Path]
    ) -> Version | None:
        event_count_by_version: dict[Version, int] = {}
        for version, version_dir in path_by_version.items():
            event_count = len(cls._get_legacy_event_files(version_dir))
            if event_count:
                logger.debug('- Version [%s] (%d events)', version, event_count)
                event_count_by_version[version] = event_count
            else:
                logger.debug('- Release [%s]: no events', version)

        if not event_count_by_version:
            return None

        version_by_id: dict[int, Version] = {
            id_: version for id_, version in enumerate(event_count_by_version, start=1)
        }
        options: dict[str, str] = {}
        for id_, version in version_by_id.items():
            event_count = event_count_by_version[version]
            events_str = ngettext(
                '{count} event', '{count} events', event_count
            ).format(count=event_count)
            options[str(id_)] = f'{version} ({events_str})'
        quit_answer: str = _('Q *** THE LETTER TO ANSWER QUIT')
        options[quit_answer] = _('Do not recover')

        version_: Version | None = None
        default_id = 1
        while True:
            choice = input_interactive_choices(
                title=_('Recover a previous version'),
                question=_('Please choose the release to recover: '),
                choices=options,
                default=str(default_id),
            )
            if choice is None:
                continue
            if choice == quit_answer:
                break
            if choice == '':
                version_ = version_by_id[default_id]
                break
            try:
                version_ = version_by_id.get(int(choice))
                if version_:
                    break
            except ValueError:
                pass
        return version_

    @classmethod
    def _recover_legacy_version(cls, version: Version, version_dir: Path):
        """Recover all the data of a previous version (configuration, events, Papi files and customization files)."""

        old_events_dir = version_dir / EVENTS_DIR.name
        old_config_file = old_events_dir / CONFIG_FILE.name
        if old_config_file.is_file():
            from gui.server_gui_toga import SharlyChessServerToga

            logger.info('Recovering configuration from release [%s]...', version)
            # copy the configuration database to its new destination
            shutil.copy(old_config_file, CONFIG_FILE)
            ConfigDatabase.setup()
            config = SharlyChessConfig()
            config.load_and_set_env()
            if SharlyChessServerToga.instance is not None:
                logger.debug('Applying recovered configuration to the Toga app...')
                SharlyChessServerToga.instance.update_from_sharly_chess_config()
            plugin_manager.reload_register()
        else:
            logger.debug(
                'Can not recover configuration from version [%s] (file [%s] not found).',
                version,
                old_config_file,
            )
        logger.info('Recovering events from release [%s]...', version)
        for file in cls._get_legacy_event_files(version_dir):
            event_uniq_id: str = file.stem
            event_database = EventDatabase(event_uniq_id)
            # copy the event database to its new destination
            shutil.copy(file, event_database.file)
            logger.debug('- Event [%s] recovered', event_uniq_id)
        if version < Version('3.0.0'):
            default_papi_dir = 'papi'
            previous_default_papi_path = version_dir / default_papi_dir
            default_papi_path = Path(default_papi_dir)
            default_papi_path.mkdir(parents=True, exist_ok=True)
            for file in previous_default_papi_path.glob('**/*.papi'):
                destination_file = default_papi_path / file.relative_to(
                    previous_default_papi_path
                )
                destination_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(file, destination_file)
        logger.info('Recovering data sources...')
        for database in LocalSourceDatabaseManager().objects():
            min_version = database.legacy_min_recovery_version
            if not min_version or version < min_version:
                continue
            src_file = version_dir / database.legacy_file_path()
            if not src_file.is_file():
                continue
            dst_file = database.file_path()
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src_file, dst_file)
            logger.debug('- Data source [%s] recovered', database.id)
        logger.info('Recovering custom files...')
        old_custom_dir: Path = version_dir / 'custom'
        if old_custom_dir.is_dir():
            for src_file in old_custom_dir.glob('**/*'):
                if not src_file.is_file():
                    continue
                relative_file = src_file.relative_to(old_custom_dir)
                dst_file = CUSTOM_DIR / relative_file
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src_file, dst_file)
                logger.debug('- Custom file [%s] recovered', relative_file)
        logger.info('Recovering archived events...')
        old_archives_dir = old_events_dir / ARCHIVES_DIR.name
        if old_archives_dir.is_dir():
            for src_file in old_archives_dir.glob(f'*.{Extension.ARCHIVE}'):
                if not src_file.is_file():
                    continue
                relative_file = src_file.relative_to(old_archives_dir)
                dst_file = ARCHIVES_DIR / relative_file
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src_file, dst_file)
                logger.debug('- Archive [%s] recovered', relative_file)

    @staticmethod
    def _recover_legacy_event_db():
        files: list[Path] = list(EVENTS_DIR.glob(f'*.{Extension.LEGACY_EVENT_DB}'))
        loader = EventLoader()
        for file in files:
            event_uniq_id = loader.get_unused_event_uniq_id(file.stem)
            logger.info('Recovering event [%s]...', event_uniq_id)
            # rename the old event database with the new extension
            file.rename(EventDatabase(event_uniq_id).file)
            # now load the new database
            EventLoader().load_event(event_uniq_id)
