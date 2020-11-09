from .shared import Sourced

# bitwise source info flags
FLAG_IS_CR = 1 << 0
FLAG_IS_UA = 1 << 1
FLAG_IS_PARTNERED = 1 << 2
FLAG_IS_NONCORE = 1 << 3


class Book(Sourced):
    def __init__(self, name, slug, flags=0, **kwargs):
        """
        :type name: str
        :type slug: str
        :type flags: int
        """
        super().__init__('book', False, page=None, **kwargs)
        self.name = name
        self.slug = slug
        self.is_cr = flags & FLAG_IS_CR
        self.is_ua = flags & FLAG_IS_UA
        self.is_partnered = flags & FLAG_IS_PARTNERED
        self.is_noncore = flags & FLAG_IS_NONCORE

    @classmethod
    def from_data(cls, d):
        return cls(d['name'], d['slug'], d.get('flags', 0),
                   source=d['source'], entity_id=d['id'], url=d['url'], is_free=d['isFree'])
