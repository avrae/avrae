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
                'characters',
                {'_id': self.character.upstream[10:]},
                {'$set': {
                    "hitPoints.adjustment": self.character.hp - self.character.max_hp}
                }, callback=update_callback)
        except MeteorClient.MeteorClientException:
            pass

    def sync_slots(self):
        spell_dict = {}
        for lvl in range(1, 10):
            spell_dict[f'level{lvl}SpellSlots.adjustment'] = \
                self.character.spellbook.get_slots(lvl) - self.character.spellbook.get_max_slots(lvl)
        try:
            DicecloudClient.getInstance().meteor_client.update('characters', {'_id': self.character.upstream[10:]},
                                                               {'$set': spell_dict},
                                                               callback=update_callback)
        except MeteorClient.MeteorClientException:
            pass

    def sync_consumable(self, consumable):
        used = consumable.value - consumable.get_max()
        try:
            if consumable.live_id in CLASS_RESOURCES:
                DicecloudClient.getInstance().meteor_client.update('characters',
                                                                   {'_id': self.character.upstream[10:]},
                                                                   {'$set': {
                                                                       f"{consumable.live_id}.adjustment": -used}},
                                                                   callback=update_callback)
            else:
                DicecloudClient.getInstance().meteor_client.update('features', {'_id': consumable.live_id},
                                                                   {'$set': {"used": used}},
                                                                   callback=update_callback)
        except MeteorClient.MeteorClientException:
            pass
