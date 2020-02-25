class Resistances:
    def __init__(self, resist=None, immune=None, vuln=None, neutral=None):
        """
        :type resist: list[Resistance]
        :type immune: list[Resistance]
        :type vuln: list[Resistance]
        :type neutral: list[Resistance]
        """
        if neutral is None:
            neutral = []
        if vuln is None:
            vuln = []
        if immune is None:
            immune = []
        if resist is None:
            resist = []
        self.resist = resist
        self.immune = immune
        self.vuln = vuln
        self.neutral = neutral

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: [Resistance.from_dict(v) for v in vs] for k, vs in d.items()})

    def to_dict(self):
        return {
            "resist": [t.to_dict() for t in self.resist],
            "immune": [t.to_dict() for t in self.immune],
            "vuln": [t.to_dict() for t in self.vuln],
            "neutral": [t.to_dict() for t in self.neutral]
        }

    def copy(self):
        return Resistances(self.resist.copy(), self.immune.copy(), self.vuln.copy(), self.neutral.copy())

    # ---------- main funcs ----------
    def __getitem__(self, item):
        if item == 'resist':
            return self.resist
        elif item == 'vuln':
            return self.vuln
        elif item == 'immune':
            return self.immune
        elif item == 'neutral':
            return self.neutral
        else:
            raise ValueError(f"{item} is not a resistance type.")

    def __str__(self):
        out = []
        if self.resist:
            out.append(f"**Resistances**: {', '.join([str(r) for r in self.resist])}")
        if self.immune:
            out.append(f"**Immunities**: {', '.join([str(r) for r in self.immune])}")
        if self.vuln:
            out.append(f"**Vulnerabilities**: {', '.join([str(r) for r in self.vuln])}")
        return '\n'.join(out)


class Resistance:
    """
    Represents a conditional resistance to a damage type.

    Only applied to a type token set T if :math:`dtype \in T \land \lnot (unless \cap T) \land only \subset T`.

    Note: transforms all damage types given to lowercase.
    """

    def __init__(self, dtype, unless=None, only=None):
        """
        :type dtype: str
        :type unless: set[str] or list[str]
        :type only: set[str] or list[str]
        """
        if unless is None:
            unless = set()
        else:
            unless = set(t.lower() for t in unless)
        if only is None:
            only = set()
        else:
            only = set(t.lower() for t in only)
        self.dtype = dtype.lower()
        self.unless = unless
        self.only = only

    @classmethod
    def from_dict(cls, d):
        if isinstance(d, str):
            return cls(d)
        return cls(**d)

    def to_dict(self):
        out = {"dtype": self.dtype}
        if self.unless:
            out['unless'] = list(self.unless)
        if self.only:
            out['only'] = list(self.only)
        return out

    def copy(self):
        return Resistance(self.dtype, self.unless.copy(), self.only.copy())

    # ---------- main funcs ----------
    def applies_to(self, tokens):
        """
        Note that tokens should be a set of lowercase strings.

        :type tokens: set[str]
        :rtype: bool
        """

        return self.dtype in tokens and not (self.unless & tokens) and self.only.issubset(tokens)

    def __str__(self):
        out = []
        out.extend(f"non{u}" for u in self.unless)
        out.extend(self.only)
        out.append(self.dtype)
        return ' '.join(out)
