import shutil
from itertools import zip_longest

from babel.messages import Catalog, Message
from babel.messages.pofile import read_po, write_po
from logging import Logger
import re
from pathlib import Path

from common.logger import get_logger

logger: Logger = get_logger()


class LocaleInfo:
    def __init__(
        self,
        id_: str,
        locale_dir: Path,
        default: bool,
        translators: list[dict[str, str | None]],
    ):
        self.id: str = id_
        self.locale_dir: Path = locale_dir
        self.default: bool = default
        self.translators: list[dict[str, str | None]] = translators
        self.po_file: Path = self.locale_dir / self.id / 'LC_MESSAGES' / 'messages.po'
        self.mo_file: Path = self.locale_dir / self.id / 'LC_MESSAGES' / 'messages.mo'
        self.messages: dict[str, Message] = {}
        self.error_messages: dict[str, Message] = {}
        self.empty_optional_messages: dict[str, Message] = {}
        self.mandatory_messages: dict[str, Message] = {}
        self.empty_mandatory_messages: dict[str, Message] = {}
        self.flagged_messages: dict[str, dict[str, Message]] = {}

    @staticmethod
    def escape_gh_md(string: str) -> str:
        """Escapes a string for GitHub markdown."""
        return string.replace('*', r'\*')

    @staticmethod
    def message_is_empty(msg: Message):
        if isinstance(msg.id, str):
            assert isinstance(msg.string, str)
            return not msg.string
        else:
            assert isinstance(msg.string, tuple)
            return not msg.string[0] or not msg.string[1]

    @staticmethod
    def sorted_tokens(string: str) -> list[str]:
        """Returns the sorted tokens of a string."""
        tokens: list[str] = []
        # ignore everything after *** (mandatory strings with instructions for the translators)
        if matches := re.match(r'^(.*)\s+\*\*\*\s+.*$', string):
            string = matches.group(1)
        # now really extract the tokens
        while True:
            token: str | None = None
            if match := re.search(r'{[^}]*}', string):  # Looking for {name}
                token = match.group()
            elif match := re.search(
                r'%%[sflt]', string
            ):  # Looking for %%s, %%f, %%l and %%t
                token = match.group()
            elif match := re.search(
                r'%[sflt]', string
            ):  # Looking for %s, %f, %l and %t
                token = match.group()
            elif match := re.search(
                r'%\([^)]*\)[ds]', string
            ):  # Looking for %(name)s or %(name)d
                token = match.group()
            if token:
                # string = string.replace(token, f'{self.token_replacement}_{len(tokens)}', 1)
                string = string.replace(token, '', 1)
                tokens.append(token)
            else:
                break
        return sorted(tokens)

    def compare_message_tokens(self, msg: Message) -> bool:
        error: bool = False
        if isinstance(msg.string, str):
            assert isinstance(msg.id, str)
            if self.sorted_tokens(msg.id) != self.sorted_tokens(msg.string):
                msg.user_comments = [
                    f'Error: tokens differ between [{msg.id}] and [{msg.string}]',
                ]
                msg.string = ''
                error = True
        else:
            assert isinstance(msg.id, tuple)
            assert isinstance(msg.string, tuple)
            for i in reversed(range(len(msg.id))):
                if self.sorted_tokens(msg.id[i]) != self.sorted_tokens(msg.string[i]):
                    msg.user_comments = [
                        f'Error: tokens differ between [{msg.id[i]}] and [{msg.string[i]}]',
                    ]
                    msg.string = tuple(
                        [
                            '',
                        ]
                        * len(msg.id)
                    )
                    error = True
                    break
        return not error

    @staticmethod
    def check_message_length(msg: Message) -> bool:
        error: bool = False
        if isinstance(msg.id, str):
            assert isinstance(msg.string, str)
            if len(msg.string) > 5 * len(msg.id):
                msg.user_comments = [
                    f'Error: translation [{msg.string}] is much too long compared to initial [{msg.id}]',
                ]
                msg.string = ''
                error = True
        else:
            assert isinstance(msg.id, tuple)
            assert isinstance(msg.string, tuple)
            for i in reversed(range(len(msg.id))):
                if len(msg.string[i]) > 5 * len(msg.id[i]):
                    msg.user_comments = [
                        f'Error: translation [{msg.string}] is much too long compared to initial [{msg.id}]',
                    ]
                    msg.string = tuple(
                        [
                            '',
                        ]
                        * len(msg.id)
                    )
                    error = True
                    break
        return not error

    def control(self):
        # Read the catalog.
        with open(self.po_file, 'rb') as f:
            catalog: Catalog = read_po(f)
        self.messages = {}
        self.error_messages = {}
        self.empty_optional_messages = {}
        self.empty_mandatory_messages = {}
        self.flagged_messages = {}
        # Control all the messages.
        for msg in catalog:
            if isinstance(msg.id, str) and msg.id:
                self.messages[msg.id] = msg
                if msg.id.__contains__('***'):
                    self.mandatory_messages[msg.id] = msg
                    if self.message_is_empty(msg):
                        self.empty_mandatory_messages[msg.id] = msg
                        continue
                else:
                    if self.message_is_empty(msg):
                        self.empty_optional_messages[msg.id] = msg
                        continue
                if not self.compare_message_tokens(msg):
                    self.error_messages[msg.id] = msg
                    continue
                if not self.check_message_length(msg):
                    self.error_messages[msg.id] = msg
                    continue
                for flag in msg.flags:
                    if flag not in [
                        'python-format',
                        'error',
                    ]:
                        if flag not in self.flagged_messages:
                            self.flagged_messages[flag] = {}
                        self.flagged_messages[flag][msg.id] = msg
        tmp_file: Path = self.po_file.with_suffix('.tmp')
        with open(tmp_file, 'wb') as f:
            write_po(f, catalog, width=0, omit_header=True)
        # compare line by line because files differ on CR/LF
        changed: bool = False
        with open(self.po_file, 'r') as before_f, open(tmp_file, 'r') as after_f:
            for before_line, after_line in zip_longest(
                before_f.readlines(), after_f.readlines()
            ):
                if before_line != after_line:
                    changed = True
        if changed:
            shutil.move(tmp_file, self.po_file)
        else:
            tmp_file.unlink()
        return changed

    def print_summary(self):
        """print a summary of the locale."""
        errors: bool = bool(
            self.error_messages
            or (not self.default and self.empty_optional_messages)
            or self.empty_mandatory_messages
            or self.flagged_messages
        )
        if errors:
            logger.info(f'- Locale [{self.id}]{" (default)" if self.default else ""}:')
        if self.error_messages:
            logger.error(f'  * Error messages ({len(self.error_messages)})')
            for msg_id in self.error_messages:
                logger.error(f'    - [{msg_id}]')
        if self.empty_mandatory_messages:
            logger.error(
                f'  * Empty mandatory messages ({len(self.empty_mandatory_messages)})'
            )
            for msg_id in self.empty_mandatory_messages:
                logger.error(f'    - [{msg_id}]')
        empty_messages_max: int = 3
        if self.empty_optional_messages and not self.default:
            logger.warning(f'  * Empty messages ({len(self.empty_optional_messages)})')
            for msg_id in list(self.empty_optional_messages.keys())[
                :empty_messages_max
            ]:
                logger.warning(f'    - [{msg_id}]')
            if len(self.empty_optional_messages) > empty_messages_max:
                logger.warning(
                    f'    - ({len(self.empty_optional_messages) - empty_messages_max} more)'
                )
        if self.flagged_messages:
            flagged_messages_max: int = 3
            for flag in sorted(self.flagged_messages.keys()):
                logger.warning(
                    f'  * Messages flagged [{flag}] ({len(self.flagged_messages[flag])})'
                )
                for msg_id in list(self.flagged_messages[flag].keys())[
                    :flagged_messages_max
                ]:
                    logger.warning(f'    - [{msg_id}]')
                if len(self.flagged_messages[flag]) > flagged_messages_max:
                    logger.warning(
                        f'    - ({len(self.flagged_messages[flag]) - flagged_messages_max} more)'
                    )
