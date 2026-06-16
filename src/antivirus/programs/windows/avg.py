from antivirus.programs.windows import WindowsAntivirus


class AVG(WindowsAntivirus):
    def __init__(self):
        super().__init__(
            name='AVG',
            doc_url='https://support.avg.com/SupportArticleView?urlName=AVG-Antivirus-scan-exclusions&supportType=home',
            signatures=[
                'avghookx.dll',
                'avghooka.dll',
            ],
        )
