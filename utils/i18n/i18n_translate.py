import re
from pathlib import Path

import requests
from babel.messages import Catalog, Message
from babel.messages.pofile import read_po, write_po
from transformers import AutoTokenizer, MarianMTModel, MarianTokenizer
from huggingface_hub import hf_hub_url

from common.i18n import default_locale
from common.logger import print_interactive_info, print_interactive_error, print_interactive_success

HF_HUB_DISABLE_SYMLINKS_WARNING = 1


class I18nTranslator:

    def __init__(
            self,
            target_locale: str,
    ):
        self.target_locale = target_locale
        self.po_file = Path() / 'locale' / target_locale / 'LC_MESSAGES' / 'messages.po'
        self.model_name: str
        if target_locale == 'pt':
            self.model_name = f'Helsinki-NLP/opus-mt-tc-big-{default_locale}-{self.target_locale}'
        else:
            self.model_name = f'Helsinki-NLP/opus-mt-{default_locale}-{self.target_locale}'
        self.model_dir = Path() / 'utils' / 'i18n' / 'models' / self.model_name
        self.catalog: Catalog | None = None
        self.model: MarianMTModel | None = None
        self.tokenizer: MarianTokenizer | None = None

    def load_catalog(self) -> bool:
        print_interactive_info(f'Loading catalog...')
        #try:
        with open(self.po_file, 'rb') as f:
            self.catalog: Catalog = read_po(f)
        print_interactive_success(f'Loaded {len(self.catalog._messages)} messages.')
        return True

    def download_file(self, filename: str) -> bool:
        self.model_dir.mkdir(parents=True, exist_ok=True)
        url: str = f'{hf_hub_url(repo_id=self.model_name, filename=filename)}?download=true'
        print_interactive_info(f'Downloading {url}...')
        r = requests.get(url, stream=True)
        if r.ok:
            output: Path = self.model_dir / filename
            with open(output, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 8):
                    if chunk:
                        f.write(chunk)
                        f.flush()
            print_interactive_success(f'Saved file {output}.')
            return True
        else:
            print_interactive_error(f'Download failed with status code {r.status_code}: {r.text}.')
            return False

    def check_model_files(self) -> bool:
        error: bool = False
        for filename in [
            'pytorch_model.bin',
            'config.json',
            'source.spm',
            'target.spm',
            'tokenizer_config.json',
            'vocab.json',
        ]:
            if not (self.model_dir / filename).is_file():
                error = error or not self.download_file(filename)
            else:
                print_interactive_success(f'{filename} found in directory {self.model_dir}.')
        return not error

    def load_translator(self) -> bool:
        print_interactive_info(f'Missing translations, loading translator {self.target_locale}...')
        print_interactive_info(f'PO locale: {default_locale}')
        print_interactive_info(f'Model: {self.model_name}')
        print_interactive_info('Checking model files...')
        if not self.check_model_files():
            return False
        try:
            print_interactive_info(f'Loading model from pretrained dataset {self.model_name}...')
            self.model = MarianMTModel.from_pretrained(self.model_name, ignore_mismatched_sizes=True)
            print_interactive_success('Model loaded.')
            print_interactive_info(f'Loading tokenizer...')
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            print_interactive_success('Tokenizer loaded.')
        except Exception as ex:
            print_interactive_error(f'{ex}')
            print_interactive_info('Loading translator failed.')
            return False
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
            elif match := re.search(r'%%[sflt]', string):  # Looking for %%s, %%f, %%l and %%t
                token = match.group()
            elif match := re.search(r'%[sflt]', string):  # Looking for %s, %f, %l and %t
                token = match.group()
            elif match := re.search(r'%\([^)]*\)[ds]', string):  # Looking for %(name)s or %(name)d
                token = match.group()
            if token:
                string = string.replace(token, f'←{len(tokens)}→', 1)
                tokens.append(token)
            else:
                break
        return string, tokens

    @staticmethod
    def inject_tokens(string: str, tokens: list[str]) -> str:
        for i in range(len(tokens)):
            string = string.replace(f'←{i}→', tokens[i], 1)
        return string

    def translate_string(
            self,
            string: str,
            percent: int,
    ) -> str:
        """ Translate a string and returns the translation. """
        # extract all the {}, %()s and %()d tokens and replace them by self.token_replacement,
        # hoping they won't be translated
        string_without_tokens, tokens = self.extract_tokens(string)
        # Call the model.
        batch = self.tokenizer([string_without_tokens, ], return_tensors='pt')
        generated_ids = self.model.generate(**batch)
        translated_string: str = self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
        # Restore the tokens previously extracted.
        translated_string_with_tokens = self.inject_tokens(translated_string, tokens)
        # Extract the tokens of the translated string.
        _, tokens_after_translation = self.extract_tokens(translated_string_with_tokens)
        # Check that the tokens are the same.
        if sorted(tokens) == sorted(tokens_after_translation):
            print_interactive_info(f'{percent}% {string} >>> {translated_string_with_tokens}')
        else:
            # Tokens have changed, delete the translation.
            print_interactive_error(f'{percent}% The tokens have changed (the translation is deleted):')
            print_interactive_error(f'{percent}% {string} >>> {translated_string_with_tokens}')
            translated_string_with_tokens = ''
        return translated_string_with_tokens

    @staticmethod
    def flag_message(message: Message, flag: str):
        """ Flags a message to indicate that it has not been translated by a human. """
        if flag not in message.flags:
            if not message.flags:
                message.flags = set()
            message.flags.add(flag)

    def translate_message(
            self,
            message: Message,
            percent: int,
    ) -> bool:
        """ Translates a message, returns True on success, False on error. """
        if isinstance(message.id, str):
            if (index := message.id.find(' ***')) != -1:
                message.string = message.id[:index]
                self.flag_message(message, 'fuzzy')
            else:
                message.string = self.translate_string(message.id, percent)
                if message.string:
                    self.flag_message(message, 'ai_translation')
                    return True
                else:
                    return False
        else:
            message.string = (
                self.translate_string(message.id[0], percent),
                self.translate_string(message.id[1], percent),
            )
            if message.string[0] and message.string[1]:
                self.flag_message(message, 'ai_translation')
                return True
            else:
                return False

    def add_missing_translations(self):
        """ Adds the missing translations, returns True if no error encountered, False Otherwise. """
        print_interactive_info(f'Adding missing translations to {self.po_file}...')
        if not self.load_catalog():
            print_interactive_error('Loading catalog failed.')
            return
        messages_to_translate: list[Message] = []
        for message in self.catalog:
            if message.id:
                if isinstance(message.id, str):
                    translate = not message.string
                else:
                    translate = not message.string[0] or not message.string[1]
                if translate:
                    messages_to_translate.append(message)
        if not messages_to_translate:
            print_interactive_info('No translation needed.')
            return True
        if not self.load_translator():
            print_interactive_error('Loading translator failed.')
            return False
        no_error: bool = True
        i: int = 0
        for message in messages_to_translate:
            i += 1
            percent = int(100 * i / len(messages_to_translate))
            if not self.translate_message(message, percent):
                no_error = False
        with open(self.po_file, 'wb') as f:
            write_po(f, self.catalog, width=0, omit_header=True)
        print_interactive_success(f'Wrote {self.po_file}.')
        return no_error


def main():
    I18nTranslator('nl').add_missing_translations()


if __name__ == '__main__':
    main()
