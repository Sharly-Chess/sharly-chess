# _Sharly Chess_ - Translation guide

See also:
- [Internationalization](i18n.md)
- [Translators](contributors.md)

## Files used for i18n

| File                                                                      | Format           | Usage                                                                   |
|---------------------------------------------------------------------------|------------------|-------------------------------------------------------------------------|
| [`/locale/babel.cfg`](../../locale/babel.cfg)                             | text / INI       | The configuration used by Babel to extraction the strings to translate. |
| `/locale/messages.pot`                                                    | text / gettext   | The Portable Object Template, common to all the translations.           |
| `/locale/<lang>/LC_MESSAGES/messages.po`                                  | text / gettext   | The Portable Object of translation `<lang>` for the core app.           |
| `/locale/<lang>/LC_MESSAGES/messages.mo`                                  | binary / gettext | The Machine Object of translation `<lang>` for the core app.            |
| `/src/plugins/<plugin>/locale/babel.cfg`                                  | text / INI       | The configuration used by Babel to extraction the strings to translate. |
| `/src/plugins/<plugin>/locale/<plugin>.pot`                               | text / gettext   | The Portable Object Template, common to all the translations.           |
| `/src/plugins/<plugin>/locale/<lang>/LC_MESSAGES/<plugin>.po`             | text / gettext   | The Portable Object of translation `<lang>` for a plugin.               |
| `/src/plugins/<plugin>/locale/<lang>/LC_MESSAGES/<plugin>.mo`             | binary / gettext | The Machine Object of translation `<lang>` for a plugin.                |
| [`/scripts/i18n/i18n_update.py`](../../scripts/i18n/i18n_update.py)       | text / Python    | The script to update translations.                                      |
| [`/scripts/i18n/i18n_translate.py`](../../scripts/i18n/i18n_translate.py) | text / Python    | The script to add new translations.                                     |

## Compiling the PO files

The human-readable PO files must be compiled to produce MO files understandable by computers at runtime (the command below must be run each time the PO files are modified):

```
python scripts/i18n/i18n_update.py
```

## Step 1 - Adding a locale

Adding a new locale is done by installing some libs and running script `i18n_translate.py`:

```
pip install -e .[translate]
python scripts/i18n/i18n_translate.py --locale pt
```

## Step 2 - Translating the application

Translating the application is then as simple as translating the PO files, that contain all the strings of the application (one PO file for the core and one for each plugin with i18n strings).

### String tokens

Some of the strings (most of them) contain tokens; the tokens are contextually replaced by the application at run-time and must be kept as-is in the translated strings.

Tokens can be:

- `{token_name}` in Python files:<br/>``{app_name} is so cool!`` > ``{app_name} est trop cool !``<br/>``Note: {note}/20`` > ``Note : {note}/20``
- `%(token_name)s` in template files:<br/>``%(app_name)s is so cool!`` > ``%(app_name)s est trop cool !``<br/>``Note: %(note)d/20`` > ``Note : %(note)d/20``

### Singular/plural

When two strings are needed for singular and plural, the strings to translate look like:

```
msgid "{locales_number} locale is currently available."
msgid_plural "{locales_number} locales are currently available."
msgstr[0] "{locales_number} langue est actuellement disponible."
msgstr[1] "{locales_number} langues sont actuellement disponibles."
```

### Mandatory translations

Some strings require special attention : they are mandatory. They contain the sub-string ``***`` and all the text from the three asterisks must be deleted from the translations:

```
msgid "Unpaired *** FEMALE"
msgstr "Non appariée"
```

### Flags

Some messages in the translation files are flagged:

- ``fuzzy``: the translations are suggested by the babel library, from the other strings found in the file;
- ``ai_translation``: translations generated using an AI.

Example:

```
#, ai_translation, fuzzy
msgid "Tournament [{tournament}] has started."
msgstr "Toernooi [{tournament}] wordt gestart."
```
These messages require a validation from the translators.

In both cases, the flags must be deleted when the proposed translations are validated or corrected.

## Step 3 - Translating new strings using an AI

When new strings are added to the application, they are untranslated. The following command can be run to automatically translate the new strings:

```
python scripts/i18n/i18n_translate.py --locale pt
```

## Technical notes for developers

The script [`/scripts/i18n/i18n_update.py`](../../scripts/i18n/i18n_update.py) does all the tasks needed to manage the translations.

### Extracting strings from the sources

Thanks to the configuration defined in [`/locale/babel.cfg`](../../locale/babel.cfg) and `/src/plugins/<plugin>/locale/babel.cfg`, strings to translate are extracted from the sources to the PO template:

- `/src/**.py`, `/src/**.j2`, `/src/web/templates/*.html` > `/locale/messages.pot`, `/src/plugins/<plugin>/locale/<plugin>.pot`

### Updating PO files

- `/locale/messages.pot` > `/locale/<locale>/LC_MESSAGES/messages.po`
- `/src/plugins/<plugin>/locale/<plugin>.pot` > `/src/plugins/<plugin>/locale/<lang>/LC_MESSAGES/<plugin>.po`

### Compiling PO files to MO files

The MO binary files (used at run-time) are compiled from the PO text files:

- `/locale/<locale>/LC_MESSAGES/messages.po` > `/locale/<locale>/LC_MESSAGES/messages.mo`
- `/src/plugins/<plugin>/locale/<lang>/LC_MESSAGES/<plugin>.po` > `/src/plugins/<plugin>/locale/<lang>/LC_MESSAGES/<plugin>.mo`

### Filling missing translations

Initial translations can be provided by models, this can be a good help for translators:

```
python scripts/i18n/i18n_translate.py --locale pt
```

See also:
- [Using models to pre-build new translations](../technical-appendices/i18n-models.md)

### References

- [Babel documentation](https://babel.pocoo.org/en/stable/)
- [Jinja2 / Babel integration](https://github.com/macagua/python_i18n_babel_jinja2)
