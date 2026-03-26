import argparse
import re
from logging import Logger, DEBUG
from pathlib import Path
from typing import Any

import requests
from babel.messages import Catalog, Message
from babel.messages.pofile import read_po, write_po
from transformers import AutoTokenizer, MarianMTModel, MarianTokenizer
from huggingface_hub import hf_hub_url


from common.i18n.babel_wrapper import BabelDomainWrapper

from common.i18n import DEFAULT_LOCALE, Domain
from common.logger import (
    print_interactive_info,
    print_interactive_error,
    print_interactive_success,
    print_interactive_warning,
    get_logger,
)

logger: Logger = get_logger()
logger.setLevel(DEBUG)

HF_HUB_DISABLE_SYMLINKS_WARNING = 1


class I18nTranslator:
    def __init__(
        self,
        target_locale: str,
    ):
        self.target_locale = target_locale
        self._model: MarianMTModel | None = None
        self._tokenizer: MarianTokenizer | None = None

    @property
    def model(self) -> MarianMTModel:
        assert self._model is not None
        return self._model

    @property
    def tokenizer(self) -> MarianTokenizer:
        assert self._tokenizer is not None
        return self._tokenizer

    def run(
        self,
    ):
        domain_message_ids_to_translate: dict[str, Any] = {}
        for domain in Domain.get_domains():
            pot_file: Path = domain.pot_file
            po_file: Path = domain.locale_po_file(self.target_locale)
            if not po_file.is_file():
                print_interactive_info(f'Creating [{po_file}] from [{pot_file}]...')
                po_file.parent.mkdir(parents=True, exist_ok=True)
                BabelDomainWrapper.run_babel_command(
                    'init',
                    [
                        f'--locale={self.target_locale}',
                        f'--input-file={pot_file}',
                        f'--output-file={po_file}',
                    ],
                )
                print_interactive_success(f'[{po_file}] created.')
            print_interactive_info(f'Updating {po_file} from the sources...')
            BabelDomainWrapper.run_babel_command(
                'update',
                [
                    f'--locale={self.target_locale}',
                    f'--output-dir={domain.locale_dir}',
                    f'--input-file={pot_file}',
                    f'--output-file={po_file}',
                    '--no-fuzzy-matching',
                    '--no-wrap',
                    '--omit-header',
                ],
            )
            print_interactive_success(f'[{po_file}] updated.')
            print_interactive_info('Loading the catalog ...')
            with open(po_file, 'rb') as f:
                catalog: Catalog = read_po(f)
            print_interactive_success(f'Loaded {len(catalog._messages)} messages.')
            print_interactive_info('Looking for messages to translate...')
            message_ids_to_translate: list[Any] = []
            for message in catalog:
                if message.id:
                    if isinstance(message.id, str):
                        assert isinstance(message.string, str)
                        translate = not message.string
                    else:
                        assert isinstance(message.string, tuple)
                        translate = not message.string[0] or not message.string[1]
                    if translate:
                        message_ids_to_translate.append(message.id)
            if not message_ids_to_translate:
                print_interactive_info(
                    f'No translation needed for domain [{domain.name}].'
                )
                continue
            domain_message_ids_to_translate[domain.name] = message_ids_to_translate
            print_interactive_success(
                f'{len(message_ids_to_translate)} messages to translate for domain [{domain.name}].'
            )
        if not domain_message_ids_to_translate:
            print_interactive_info('No translation needed, exiting.')
            return
        print_interactive_success(
            f'{sum(len(messages_to_translate) for messages_to_translate in domain_message_ids_to_translate.values())} messages to translate.'
        )
        if not self.init_tools():
            return
        for domain in Domain.get_domains():
            if domain.name in domain_message_ids_to_translate:
                po_file: Path = domain.locale_po_file(self.target_locale)
                print_interactive_success(f'Reading catalog [{po_file}]...')
                with open(po_file, 'rb') as f:
                    catalog: Catalog = read_po(f)
                print_interactive_success(
                    f'Adding missing translations to [{po_file}]...'
                )
                error: bool = False
                i: int = 0
                for message_id in domain_message_ids_to_translate[domain.name]:
                    i += 1
                    percent = int(
                        100 * i / len(domain_message_ids_to_translate[domain.name])
                    )
                    if not self.translate_message(
                        catalog._messages[
                            message_id if isinstance(message_id, str) else message_id[0]
                        ],
                        percent,
                    ):
                        error = True
                with open(po_file, 'wb') as f:
                    write_po(f, catalog, width=0, omit_header=True)
                print_interactive_success(f'Wrote {po_file}.')
                if error:
                    print_interactive_warning(f'Errors found, please check {po_file}.')
                mo_file: Path = po_file.with_suffix('.mo')
                print_interactive_success(f'Compiling [{po_file}] to [{mo_file}]...')
                BabelDomainWrapper.run_babel_command(
                    'compile',
                    [
                        f'--domain={domain.name}',
                        f'--directory={domain.locale_dir}',
                        f'--locale={self.target_locale}',
                        '--use-fuzzy',
                    ],
                    verbose=True,
                )
                print_interactive_success(f'Written [{mo_file}]...')

    def init_tools(self) -> bool:
        model_name: str
        if self.target_locale == 'pt':
            model_name = (
                f'Helsinki-NLP/opus-mt-tc-big-{DEFAULT_LOCALE}-{self.target_locale}'
            )
        else:
            model_name = f'Helsinki-NLP/opus-mt-{DEFAULT_LOCALE}-{self.target_locale}'
        print_interactive_info(
            f'Looking for the translator from [{DEFAULT_LOCALE}] to {self.target_locale} (model: {model_name})...'
        )
        model_dir: Path = Path() / 'scripts' / 'i18n' / 'models' / model_name
        for filename in [
            'pytorch_model.bin',
            'config.json',
            'source.spm',
            'target.spm',
            'tokenizer_config.json',
            'vocab.json',
        ]:
            if (model_dir / filename).is_file():
                print_interactive_success(f'{filename} found in directory {model_dir}.')
                continue
            model_dir.mkdir(parents=True, exist_ok=True)
            url: str = (
                f'{hf_hub_url(repo_id=model_name, filename=filename)}?download=true'
            )
            print_interactive_info(f'Downloading {url}...')
            r = requests.get(url, stream=True)
            if not r.ok:
                print_interactive_error(
                    f'Download failed with status code {r.status_code}: {r.text}, exiting.'
                )
                return False
            output: Path = model_dir / filename
            with open(output, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 8):
                    if chunk:
                        f.write(chunk)
                        f.flush()
            print_interactive_info(f'Saved file {output}.')
        print_interactive_success(f'Model {model_name} OK.')
        print_interactive_info('Loading model from pretrained dataset...')
        self._model: MarianMTModel = MarianMTModel.from_pretrained(
            model_name, ignore_mismatched_sizes=True
        )
        print_interactive_success('Model loaded.')
        print_interactive_info('Loading tokenizer...')
        self._tokenizer: MarianTokenizer = AutoTokenizer.from_pretrained(model_name)
        print_interactive_success('Tokenizer loaded.')
        return True

    @staticmethod
    def extract_tokens(string: str) -> tuple[str, list[str]]:
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
                string = string.replace(token, f'({len(tokens)})', 1)
                tokens.append(token)
            else:
                break
        return string, tokens

    @staticmethod
    def inject_tokens(string: str, tokens: list[str]) -> str:
        for i in range(len(tokens)):
            string = string.replace(f'({i})', tokens[i], 1)
        return string

    def translate_string(
        self,
        string: str,
        percent: int,
    ) -> str:
        """Translate a string and returns the translation."""
        # extract all the {}, %()s and %()d tokens and replace them by self.token_replacement,
        # hoping they won't be translated
        string_without_tokens, tokens = self.extract_tokens(string)
        # Call the model.
        batch = self.tokenizer(
            [
                string_without_tokens,
            ],
            return_tensors='pt',
        )
        generated_ids = self.model.generate(**batch)
        translated_string: str = self.tokenizer.batch_decode(
            generated_ids, skip_special_tokens=True
        )[0]
        # Restore the tokens previously extracted.
        translated_string_with_tokens = self.inject_tokens(translated_string, tokens)
        # Extract the tokens of the translated string.
        _, tokens_after_translation = self.extract_tokens(translated_string_with_tokens)
        # Check that the tokens are the same.
        if sorted(tokens) == sorted(tokens_after_translation):
            print_interactive_info(
                f'{percent}% {string} >>> {translated_string_with_tokens}'
            )
        else:
            # Tokens have changed, delete the translation.
            print_interactive_warning(
                f'{percent}% The tokens have changed (the translation should be manually updated):'
            )
            print_interactive_warning(
                f'{percent}% {string} >>> {translated_string_with_tokens}'
            )
        return translated_string_with_tokens

    @staticmethod
    def flag_message(message: Message, flag: str):
        """Flags a message to indicate that it has not been translated by a human."""
        if flag not in message.flags:
            if not message.flags:
                message.flags = set()
            message.flags.add(flag)

    def translate_message(
        self,
        message: Message,
        percent: int,
    ) -> bool:
        """Translates a message, returns True on success, False on error."""
        if isinstance(message.id, str):
            if (index := message.id.find(' ***')) != -1:
                message.string = message.id[:index]
                self.flag_message(message, 'fuzzy')
                return True
            else:
                message.string = self.translate_string(message.id, percent)
                if message.string:
                    self.flag_message(message, 'ai_translation')
                    return True
                else:
                    return False
        elif isinstance(message.id, tuple):
            assert len(message.id) == 2, f'{message.id=}'
            message.string = (
                self.translate_string(message.id[0], percent),
                self.translate_string(message.id[1], percent),
            )
            if message.string[0] and message.string[1]:
                self.flag_message(message, 'ai_translation')
                return True
            else:
                return False
        else:
            logger.warning(
                'Can not translate message [%s] (type: [%s])',
                message.id,
                type(message.id),
            )
            return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-l',
        '--locale',
        type=str,
        help='the locale to translate',
        required=True,
    )
    args = parser.parse_args()

    I18nTranslator(args.locale).run()
