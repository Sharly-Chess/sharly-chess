from antivirus.programs.windows import WindowsAntivirus


class Kaspersky(WindowsAntivirus):
    def __init__(self):
        super().__init__(
            name='Kaspersky',
            doc_url='https://support.kaspersky.com/ksws/11/en-US/179387.htm',
            signatures=[
                'kav.exe',
                'kavsvc.exe',
            ],
        )
