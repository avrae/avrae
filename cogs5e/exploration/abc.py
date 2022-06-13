class SheetLoaderABC:
    def __init__(self, url):
        self.url = url
        self.encounter_data = None

    async def load_encounter(self, ctx, args):
        raise NotImplemented
