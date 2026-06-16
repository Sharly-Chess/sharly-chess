from antivirus.programs.windows import WindowsAntivirus


class FSecure(WindowsAntivirus):
    def __init__(self):
        super().__init__(
            name='F-Secure',
            doc_url='https://help.f-secure.com/product.html#home/total-windows/latest/en/task_13205052E3D44C44BA2491A55A7F818F-latest-en',
            signatures=[
                'fsav.exe',
                'fsgk32.exe',
            ],
        )
