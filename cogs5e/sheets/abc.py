class SheetLoaderABC:
    def __init__(self, url):
        self.url = url
        self.character_data = None

    async def load_character(self, owner_id: str, args):
        raise NotImplemented
