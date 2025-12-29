from typing import Self


class Translator:
    def __init__(
        self,
        github_user: str | None = None,
        name: str | None = None,
    ):
        self.github_user: str | None = github_user
        self.name: str = name or 'Unknown'

    @classmethod
    def get_translators(
        cls,
        locales: list[str],
    ) -> dict[str, list[Self]]:
        # The translators (assigned to the locales).
        translators: dict[str, list[Self]] = {
            'en': [
                cls('timothyarmes', 'Timothy ARMES'),
            ],
            'fr': [
                cls('pascalaubry', 'Pascal AUBRY'),
                cls('Amaras', 'Sammy PLAT'),
            ],
            'pt': [
                cls('emerson-proenca', 'Emerson Proença'),
            ],
        }
        return translators | {
            locale: [
                cls(),
            ]
            for locale in locales
            if locale not in translators
        }
