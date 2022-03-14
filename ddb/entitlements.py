class UserEntitlements:
    __slots__ = ("acquired_license_ids", "shared_licenses")

    def __init__(self, acquired_license_ids, shared_licenses):
        """
        :type acquired_license_ids: list[int]
        :type shared_licenses: list[SharedLicense]
        """
        self.acquired_license_ids = acquired_license_ids
        self.shared_licenses = shared_licenses

    @classmethod
    def from_dict(cls, d):
        return cls(d["acquiredLicenseIDs"], [SharedLicense.from_dict(sl) for sl in d["sharedLicenses"]])

    def to_dict(self):
        return {
            "acquiredLicenseIDs": self.acquired_license_ids,
            "sharedLicenses": [sl.to_dict() for sl in self.shared_licenses],
        }

    @property
    def licenses(self):
        """
        The set of all license IDs the user has access to.
        :rtype: set[int]
        """
        return set(self.acquired_license_ids).union(*(sl.license_ids for sl in self.shared_licenses))


class SharedLicense:
    __slots__ = ("campaign_id", "license_ids")

    def __init__(self, campaign_id, license_ids):
        """
        :type campaign_id: int
        :type license_ids: list[int]
        """
        self.campaign_id = campaign_id
        self.license_ids = license_ids

    @classmethod
    def from_dict(cls, d):
        return cls(d["campaignID"], d["licenseIDs"])

    def to_dict(self):
        return {"campaignID": self.campaign_id, "licenseIDs": self.license_ids}


class EntityEntitlements:
    __slots__ = ("entity_type", "entity_id", "is_free", "license_ids")

    def __init__(self, entity_type, entity_id, is_free, license_ids):
        """
        :type entity_type: str
        :type entity_id: int
        :type is_free: bool
        :type license_ids: set[int]
        """
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.is_free = is_free
        self.license_ids = set(license_ids)

    @classmethod
    def from_dict(cls, d):
        return cls(d["entityType"], int(d["entityID"]), d["isFree"], d["licenseIDs"])

    def to_dict(self):
        return {
            "entityType": self.entity_type,
            "entityID": self.entity_id,
            "isFree": self.is_free,
            "licenseIDs": list(self.license_ids),
        }
