import abc


class Sourced(abc.ABC):
    """A base class for entities with a source."""
    name = ...

    def __init__(self, entity_type: str, homebrew: bool, source: str, entity_id: int = None,
                 page: int = None, url: str = None,
                 is_free: bool = False, entitlement_entity_type: str = None, entitlement_entity_id: int = None,
                 parent=None):
        """
        :param entity_type: The type of this entity.
        :param homebrew: Whether or not this entity is homebrew.
        :param source: The abbreviated source this entity comes from.
        :param entity_id: The DDB Entity ID
        :param page: The page number from that source this entity can be found on.
        :param url: The URL that this entity can be found at.
        :param is_free: Whether or not this entity requires a purchase to view.
        :param entitlement_entity_type: If this entity's access is controlled by access to another entity, the type of that entuty.
        :param entitlement_entity_id: The entity ID of the entitlement entity.
        :param Sourced parent: If this entity comes from some other entity, its parent.
        """
        self.entity_type = entity_type
        self.homebrew = homebrew
        self.source = source
        self.entity_id = entity_id
        self.page = page
        self._url = url
        self.is_free = is_free or homebrew
        self.entitlement_entity_type = entitlement_entity_type or entity_type
        self.entitlement_entity_id = entitlement_entity_id or entity_id
        self.parent = parent

    def source_str(self):
        if self.page is None:
            return self.source
        return f"{self.source} {self.page}"  # e.g. "PHB 196"

    @property
    def url(self):
        """Returns the reference URL for this sourced object."""
        if self._url:
            return f"{self._url}?utm_source=avrae&utm_medium=reference"
        return None

    @property
    def marketplace_url(self):
        """Returns the marketplace URL for this sourced object."""
        if self._url:
            return f"{self._url}?utm_source=avrae&utm_medium=marketplacelink"
        return f"https://www.dndbeyond.com/marketplace?utm_source=avrae&utm_medium=marketplacelink"

    def __repr__(self):
        return f"<{type(self).__name__} name={self.name!r} entity_id={self.entity_id!r} " \
               f"entity_type={self.entity_type!r} url={self._url!r}>"


class Trait:
    def __init__(self, name, text):
        self.name = name
        self.text = text

    @classmethod
    def from_dict(cls, d):
        return cls(d['name'], d['text'])
