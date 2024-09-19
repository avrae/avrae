import abc

__all__ = ("Sourced", "Trait", "LimitedUse", "CachedSourced")


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
        is_legacy: bool = False,
        entitlement_entity_type: str = None,
        entitlement_entity_id: int = None,
        limited_use_only: bool = False,
        rulesVersion: str = None,
    ):
        """
        :param homebrew: Whether or not this entity is homebrew.
        :param source: The abbreviated source this entity comes from.
        :param entity_id: The DDB Entity ID
        :param page: The page number from that source this entity can be found on.
        :param url: The URL that this entity can be found at.
        :param is_free: Whether or not this entity requires a purchase to view.
        :param is_legacy: Whether this entity is a legacy entity.
        :param entitlement_entity_type: If this entity's access is controlled by access to another entity, the type of that entity.
        :param entitlement_entity_id: The entity ID of the entitlement entity.
        :param limited_use_only: Whether this entity is to be used for limited use only, or be allowed in lookup
        """
        self.homebrew = homebrew
        self.source = source
        self.entity_id = entity_id
        self.page = page
        self._url = url
        self.is_free = is_free or homebrew
        self.is_legacy = is_legacy
        self.entitlement_entity_type = entitlement_entity_type or self.entity_type
        self.entitlement_entity_id = entitlement_entity_id or entity_id
        self.limited_use_only = limited_use_only
        self.rulesVersion = rulesVersion

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
            f"entity_type={self.entity_type!r} url={self._url!r} limited_use_only={self.limited_use_only!r}>"
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
            is_legacy=parent.is_legacy,
            url=parent.raw_url,
            entitlement_entity_id=parent.entitlement_entity_id,
            entitlement_entity_type=parent.entitlement_entity_type,
        )


class CachedSourced(Sourced):
    def __init__(self, name, entity_type, has_image=False, has_token=False, **kwargs):
        self.name = name
        self.entity_type = entity_type
        self.has_image = has_image
        self.has_token = has_token
        Sourced.__init__(
            self,
            homebrew=kwargs["homebrew"],
            source=kwargs["source"],
            entity_id=kwargs.get("entity_id"),
            page=kwargs.get("page"),
            url=kwargs.get("url"),
            is_free=kwargs.get("is_free"),
            is_legacy=kwargs.get("is_legacy"),
        )

    @classmethod
    def from_dict(cls, d):
        return cls(
            d["name"],
            d["entity_type"],
            d.get("has_image", False),
            d.get("has_token", False),
            homebrew=d["homebrew"],
            source=d["source"],
            entity_id=d["entity_id"],
            is_free=d["is_free"],
            is_legacy=d["is_legacy"],
        )

    def to_dict(self):
        return {
            "name": self.name,
            "entity_type": self.entity_type,
            "has_image": self.has_image,
            "has_token": self.has_token,
            "homebrew": self.homebrew,
            "source": self.source,
            "entity_id": self.entity_id,
            "is_free": self.is_free,
            "is_legacy": self.is_legacy,
        }
