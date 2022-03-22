import abc

__all__ = ("Sourced", "Trait", "LimitedUse")


class Sourced(abc.ABC):
    """A base class for entities with a source."""

    name = ...
    entity_type = ...
    type_id = ...

    def __init__(
        self,
        homebrew: bool,
        source: str,
        entity_id: int = None,
        page: int = None,
        url: str = None,
        is_free: bool = False,
        entitlement_entity_type: str = None,
        entitlement_entity_id: int = None,
    ):
        """
        :param homebrew: Whether or not this entity is homebrew.
        :param source: The abbreviated source this entity comes from.
        :param entity_id: The DDB Entity ID
        :param page: The page number from that source this entity can be found on.
        :param url: The URL that this entity can be found at.
        :param is_free: Whether or not this entity requires a purchase to view.
        :param entitlement_entity_type: If this entity's access is controlled by access to another entity, the type of that entuty.
        :param entitlement_entity_id: The entity ID of the entitlement entity.
        """
        self.homebrew = homebrew
        self.source = source
        self.entity_id = entity_id
        self.page = page
        self._url = url
        self.is_free = is_free or homebrew
        self.entitlement_entity_type = entitlement_entity_type or self.entity_type
        self.entitlement_entity_id = entitlement_entity_id or entity_id

    @classmethod
    def lookup(cls, entity_id: int):
        """Utility method to look up an instance of this class from the compendium."""
        from gamedata.compendium import compendium

        return compendium.lookup_entity(cls.entity_type, entity_id)

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

    @property
    def raw_url(self):
        return self._url

    def __repr__(self):
        return (
            f"<{type(self).__name__} name={self.name!r} entity_id={self.entity_id!r} "
            f"entity_type={self.entity_type!r} url={self._url!r}>"
        )


class Trait:
    def __init__(self, name, text):
        self.name = name
        self.text = text

    @classmethod
    def from_dict(cls, d):
        return cls(d["name"], d["text"])


class LimitedUse(Sourced):
    entity_type = "limited-use"
    type_id = 222216831

    def __init__(self, name, parent, type_id=None, **kwargs):
        super().__init__(homebrew=False, **kwargs)
        self.name = name
        self.parent = parent
        if type_id is not None:
            self.type_id = type_id

    @classmethod
    def from_dict(cls, d, parent):
        return cls(
            d["name"],
            parent=parent,
            type_id=d.get("type_id"),
            entity_id=d["id"],
            page=parent.page,
            source=parent.source,
            is_free=parent.is_free,
            url=parent.raw_url,
            entitlement_entity_id=parent.entitlement_entity_id,
            entitlement_entity_type=parent.entitlement_entity_type,
        )
