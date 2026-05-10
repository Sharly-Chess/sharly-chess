from antivirus.programs.windows import WindowsAntivirus


class Avira(WindowsAntivirus):
    def __init__(self):
        super().__init__(
            name='Avira',
            doc_url='https://www.avira.com/en/blog/exceptions-avira-antivirus-3-steps',
            signatures=[
                'avguard.exe',
                'avscan.exe',
            ],
        )
