from antivirus.programs.windows import WindowsAntivirus


class Norton(WindowsAntivirus):
    def __init__(self):
        super().__init__(
            name='Norton',
            doc_url='https://support.norton.com/sp/en/us/home/current/solutions/v20240108162522348',
            signatures=[
                'ccSvcHst.exe',
                'norton.exe',
            ],
        )
