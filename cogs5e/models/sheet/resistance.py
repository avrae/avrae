import re

import d20

from utils.constants import RESIST_TYPES


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
    def from_dict(cls, d, smart=True):
        return cls(**{k: [Resistance.from_dict(v, smart) for v in vs] for k, vs in d.items()})

    @classmethod
    def from_args(cls, args, **kwargs):
        return cls.from_dict({
            'resist': args.get('resist', [], **kwargs),
            'immune': args.get('immune', [], **kwargs),
            'vuln': args.get('vuln', [], **kwargs),
            'neutral': args.get('neutral', [], **kwargs)
        })

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
    def update(self, other, overwrite=True):
        """
        Updates this Resistances with the resistances of another.

        :param overwrite: If a damage type is specified in the other, removes all occurances of that type in this one.
        :type other: Resistances
        """
        to_remove = set(r.dtype for rt in RESIST_TYPES for r in other[rt])  # set of all damage types specified in other

        for rt in RESIST_TYPES:
            # remove all instances of damage types to remove from me
            if overwrite:
                for resist in reversed(self[rt]):
                    if resist.dtype in to_remove:
                        self[rt].remove(resist)

            # and add the resistances from the other
            self[rt].extend(other[rt])

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
    def from_dict(cls, d, smart=True):
        if isinstance(d, str):
            return cls.from_str(d, smart)
        return cls(**d)

    @classmethod
    def from_str(cls, s, smart=True):
        if not smart:
            return cls(s)

        tokens = _resist_tokenize(s)
        if not tokens:  # weird edge case of resistance of only punctuation
            return cls(s)

        unless = []
        only = []
        for t in tokens[:-1]:
            if t.startswith('non') and len(t) > 3:
                unless.append(t[3:])
            else:
                only.append(t)
        return cls(tokens[-1], unless=unless, only=only)

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
    def applies_to_str(self, dtype):
        """
        Returns whether or not this resistance is applicable to a damage type.

        :param dtype: The damage type to test.
        :type dtype: str
        :rtype: bool
        """
        return self.applies_to(set(t.lower() for t in _resist_tokenize(dtype)))

    def applies_to(self, tokens):
        """
        Note that tokens should be a set of lowercase strings.

        :param tokens: A set of strings to test against.
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

    def __repr__(self):
        return f"<Resistance {repr(self.dtype)} unless={repr(self.unless)} only={repr(self.only)}>"


def _resist_tokenize(res_str):
    """Extracts a list of tokens from a string (any consecutive chain of letters)."""
    return [m.group(0) for m in re.finditer(r'\w+', res_str)]


def do_resistances(damage_expr, resistances, always=None, transforms=None):
    """
    Modifies a dice expression in place, inserting binary operations where necessary to handle resistances to given
    damage types.

    Note that any neutrals in the resistances will be explicitly ignored.

    :type damage_expr: d20.Expression
    :type resistances: Resistances
    :param always: If passed, damage is always this type in addition to whatever it's annotated as.
    :type always: set[str]
    :param transforms: a dict representing damage type transforms. If None is a key, all damage types become that.
    :type transforms: dict[str or None, str]
    """
    if always is None:
        always = set()
    if transforms is None:
        transforms = {}

    # simplify damage types
    d20.utils.simplify_expr_annotations(damage_expr.roll, ambig_inherit='left')

    # depth first visit expression nodes: if it has an annotation, add the appropriate binops and move to the next
    def do_visit(node):
        if node.annotation:
            # handle transforms
            if None in transforms:
                tokens = _resist_tokenize(transforms[None])
            else:
                tokens = []
                for t in _resist_tokenize(node.annotation.lower()):
                    tokens.extend(_resist_tokenize(transforms.get(t, t)))
            original_annotation = node.annotation
            dtype = f"{' '.join(always)} {' '.join(tokens)}".strip()
            node.annotation = f"[{dtype}]"

            # handle tree modification
            ann = set(tokens) | always

            if any(n.applies_to(ann) for n in resistances.neutral):  # neutral overrides all
                return node

            if any(v.applies_to(ann) for v in resistances.vuln):
                node = d20.BinOp(d20.Parenthetical(node), '*', d20.Literal(2))

            if original_annotation.startswith('[^') or original_annotation.endswith('^]'):
                node.annotation = original_annotation
                # break here - don't handle resist/immune
                return node

            if any(r.applies_to(ann) for r in resistances.resist):
                node = d20.BinOp(d20.Parenthetical(node), '/', d20.Literal(2))

            if any(im.applies_to(ann) for im in resistances.immune):
                node = d20.BinOp(d20.Parenthetical(node), '*', d20.Literal(0))

            return node

        for i, child in enumerate(node.children):
            replacement = do_visit(child)
            if replacement and replacement is not child:
                node.set_child(i, replacement)
        return None

    do_visit(damage_expr)


if __name__ == '__main__':
    import traceback

    resists = Resistances(resist=[Resistance('resist', ['magical']), Resistance('both')],
                          immune=[Resistance('immune'), Resistance('this', only=['magical'])],
                          vuln=[Resistance('vuln'), Resistance('both')],
                          neutral=[Resistance('neutral')])

    while True:
        try:
            result = d20.roll(input())
            print(str(result))
            do_resistances(result.expr, resists)
            print(d20.MarkdownStringifier().stringify(result.expr))
        except Exception as e:
            traceback.print_exc()
