import logging

import MeteorClient

from cogs5e.models.dicecloud.client import DicecloudClient
from cogs5e.models.sheet.integrations import LiveIntegration

log = logging.getLogger(__name__)

CLASS_RESOURCES = ("expertiseDice", "ki", "rages", "sorceryPoints", "superiorityDice")


def update_callback(error, data):
    if error:
        log.warning(error)
    else:
        log.debug(data)


class DicecloudIntegration(LiveIntegration):
    def sync_hp(self):
        try:
            DicecloudClient.getInstance().meteor_client.update(
                'self.characters',
                {'_id': self.character.upstream[10:]},
                {'$set': {
                    "hitPoints.adjustment": self.character.get_current_hp() - self.character.get_max_hp()}
                }, callback=update_callback)
        except MeteorClient.MeteorClientException:
            pass

    def sync_slots(self):
        spell_dict = {}
        for lvl in range(1, 10):
            spell_dict[f'level{lvl}SpellSlots.adjustment'] = \
                self.character.get_remaining_slots(lvl) - self.character.get_max_spellslots(lvl)
        try:
            DicecloudClient.getInstance().meteor_client.update('self.characters', {'_id': self.character.upstream[10:]},
                                                               {'$set': spell_dict},
                                                               callback=update_callback)
        except MeteorClient.MeteorClientException:
            pass

    def sync_consumable(self, consumable):
        used = consumable.value - consumable.max
        try:
            if consumable.sync_id in CLASS_RESOURCES:
                DicecloudClient.getInstance().meteor_client.update('self.characters',
                                                                   {'_id': self.character.upstream[10:]},
                                                                   {'$set': {
                                                                       f"{consumable.sync_id}.adjustment": -used}},
                                                                   callback=update_callback)
            else:
                DicecloudClient.getInstance().meteor_client.update('features', {'_id': consumable.sync_id},
                                                                   {'$set': {"used": used}},
                                                                   callback=update_callback)
        except MeteorClient.MeteorClientException:
            pass
