from typing import List, Optional, Union

from ddb.utils import ApiBaseModel


class SimplifiedAbility(ApiBaseModel):
    name: str
    label: str
    score: int
    modifier: int
    save: int


class SimplifiedRange(ApiBaseModel):
    label: str
    long_range_value: Optional[int]
    value: Optional[int]
    origin: Optional[str]


class SimplifiedDice(ApiBaseModel):
    dice_count: int
    dice_value: int
    fixed_value: int
    dice_string: Optional[str]
    dice_multiplier: Optional[int]


class SimplifiedDamage(ApiBaseModel):
    type: Optional[str]
    value: Optional[Union[SimplifiedDice, int]]


class SimplifiedAttackSaveInfo(ApiBaseModel):
    value: int
    label: str


class SimplifiedAttack(ApiBaseModel):
    name: str
    range: SimplifiedRange
    damage: SimplifiedDamage
    save_info: Optional[SimplifiedAttackSaveInfo]
    to_hit: Optional[int]


class SimplifiedAttunedItem(ApiBaseModel):
    name: str
    definition_key: str
    type: str
    avatar_url: str


class SimplifiedCampaign(ApiBaseModel):
    name: str
    id: int
    url: str
    dm_user_id: int


class SimplifiedCastingValue(ApiBaseModel):
    value: int
    sources: List[str]


class SimplifiedCastingInfo(ApiBaseModel):
    modifiers: List[SimplifiedCastingValue]
    save_dcs: List[SimplifiedCastingValue]
    spell_attacks: List[SimplifiedCastingValue]


class SimplifiedCondition(ApiBaseModel):
    name: str
    level: Optional[int]


class SimplifiedClass(ApiBaseModel):
    name: str
    level: int
    subclass_name: Optional[str]


class SimplifiedDeathSaveInfo(ApiBaseModel):
    fail_count: int
    success_count: int


class SimplifiedHitPointInfo(ApiBaseModel):
    current: int
    maximum: int
    temp: int


class SimplifiedDamageAdjustment(ApiBaseModel):
    name: str
    type: int


class SimplifiedProficiencyGroup(ApiBaseModel):
    group: str
    values: str


class SimplifiedRace(ApiBaseModel):
    name: str


class SimplifiedSense(ApiBaseModel):
    name: str
    value: str


class SimplifiedSkill(ApiBaseModel):
    name: str
    modifier: int
    is_proficient: bool
    is_half_proficient: bool
    is_expert: bool
    is_advantage: bool
    is_disadvantage: bool


class SimplifiedSpeed(ApiBaseModel):
    name: str
    distance: int


class SimplifiedCharacterData(ApiBaseModel):
    abilities: List[SimplifiedAbility]
    armor_class: int
    attacks: List[SimplifiedAttack]
    attuned_items: List[SimplifiedAttunedItem]
    campaign: Optional[SimplifiedCampaign]
    casting_info: SimplifiedCastingInfo
    character_id: int
    conditions: List[SimplifiedCondition]
    classes: List[SimplifiedClass]
    current_xp: Optional[int]
    death_save_info: SimplifiedDeathSaveInfo
    hit_point_info: SimplifiedHitPointInfo
    immunities: List[SimplifiedDamageAdjustment]
    initiative_bonus: int
    inspiration: bool
    level: int
    name: str
    passive_investigation: int
    passive_insight: int
    passive_perception: int
    proficiency_bonus: int
    proficiency_groups: List[SimplifiedProficiencyGroup]
    race: SimplifiedRace
    read_only_url: str
    resistances: List[SimplifiedDamageAdjustment]
    senses: List[SimplifiedSense]
    skills: List[SimplifiedSkill]
    speeds: List[SimplifiedSpeed]
    user_id: int
    vulnerabilities: List[SimplifiedDamageAdjustment]
