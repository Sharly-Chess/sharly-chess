from antivirus.programs.windows import WindowsAntivirus


class ESET(WindowsAntivirus):
    def __init__(self):
        super().__init__(
            name='ESET',
            doc_url='https://help.eset.com/ees/10.1/en-US/idh_config_processes_exclude_add.html?idh_config_amon.html',
            signatures=[
                'Efwd.exe',
                'ekrn.exe',
                'eServiceHost.exe',
            ],
        )
