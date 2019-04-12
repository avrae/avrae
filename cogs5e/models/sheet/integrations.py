class LiveIntegration:
    def __init__(self, character):
        self.character = character

    def sync_hp(self):
        raise NotImplemented

    def sync_slots(self):
        raise NotImplemented

    def sync_consumable(self, consumable):
        raise NotImplemented
