class PapiWebException(Exception):
    def __init__(self, string: str):
        super().__init__(string)
