from .shared import Sourced


class Item(Sourced):
    def __init__(self, name, desc, attunement, meta=None, image=None, **kwargs):
        """
        :type name: str
        :type desc: str
        :type attunement: bool or str
        :type meta: str or None
        :type image: str or None
        """
        super().__init__('item', False, **kwargs)
        self.name = name
        self.desc = desc
        self.attunement = attunement
        self.meta = meta
        self.image = image

    @classmethod
    def from_data(cls, d):
        return cls(d['name'], d['desc'], d['attunement'],
                   d.get('meta'), d.get('image'),
                   source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'], is_free=d['isFree'])
