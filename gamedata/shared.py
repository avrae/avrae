import abc

from utils.functions import source_slug


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
        self._url = url
        self.is_free = is_free or homebrew

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
        elif slug := source_slug(self.source):
            return f"https://www.dndbeyond.com/marketplace/sources/{slug}?utm_source=avrae&utm_medium=marketplacelink"
        return f"https://www.dndbeyond.com/marketplace?utm_source=avrae&utm_medium=marketplacelink"

    def __repr__(self):
        return f"<{type(self).__name__} entity_id={self.entity_id} entity_type={self.entity_type} {self._url}>"


class Trait:
    def __init__(self, name, text):
        self.name = name
        self.text = text

    @classmethod
    def from_dict(cls, d):
        return cls(d['name'], d['text'])


class SourcedTrait(Trait, Sourced):
    def __init__(self, name, text, **kwargs):
        Sourced.__init__(self, **kwargs)
        Trait.__init__(self, name, text)

    @classmethod
    def from_trait_and_sourced(cls, trait, sourced, entity_type=None, homebrew=None):
        if entity_type is None:
            # copy the source parent's entity type
            # even if this entity isn't of that kind, we need to use the parent's entity type
            # in entitlements checks
            entity_type = sourced.entity_type
        if homebrew is None:
            homebrew = sourced.homebrew
        return cls(
            trait.name, trait.text,
            entity_type=entity_type, homebrew=homebrew,
            source=sourced.source, entity_id=sourced.entity_id, page=sourced.page, url=sourced._url,
            is_free=sourced.is_free
        )

    @classmethod
    def from_trait_and_sourced_dicts(cls, trait, sourced, entity_type, homebrew=False):
        return cls(
            trait['name'], trait['text'],
            entity_type=entity_type, homebrew=homebrew,
            source=trait.get('source', sourced['source']), entity_id=trait.get('id', sourced['id']),
            page=trait.get('page', sourced['page']), url=trait.get('url', sourced['url']),
            is_free=trait.get('isFree', sourced['isFree'])
        )
