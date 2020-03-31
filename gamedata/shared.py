import abc


class Sourced(abc.ABC):
    """A base class for entities with a source."""

    def __init__(self, entity_type: str, homebrew: bool, source: str, entity_id: int = None,
                 page: int = None, url: str = None, is_free: bool = False):
        """
        :param entity_type: The type of this entity.
        :param homebrew: Whether or not this entity is homebrew.
        :param source: The abbreviated source this entity comes from.
        :param entity_id: The DDB Entity ID
        :param page: The page number from that source this entity can be found on.
        :param url: The URL that this entity can be found at.
        :param is_free: Whether or not this entity requires a purchase to view.
        """
        self.entity_type = entity_type
        self.homebrew = homebrew
        self.source = source
        self.entity_id = entity_id
        self.page = page
        self.url = url
        self.is_free = is_free or homebrew

    def source_str(self):
        if self.page is None:
            return self.source
        return f"{self.source} {self.page}"  # e.g. "PHB 196"


class Trait:
    def __init__(self, name, text):
        self.name = name
        self.text = text

    @classmethod
    def from_dict(cls, d):
        return cls(d['name'], d['text'])
