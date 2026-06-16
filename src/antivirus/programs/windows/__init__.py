from antivirus.programs.antivirus import Antivirus


class WindowsAntivirus(Antivirus):
    def __init__(
        self,
        name: str,
        doc_url: str,
        signatures: list[str],
    ):
        super().__init__(name, doc_url, signatures)
