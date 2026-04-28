from contextlib import contextmanager
from contextvars import ContextVar, Token

_attack_display_depth: ContextVar[int] = ContextVar("attack_display_depth", default=0)


def attack_display_depth() -> int:
    return _attack_display_depth.get()


@contextmanager
def attack_display_guard():
    token: Token[int] = _attack_display_depth.set(_attack_display_depth.get() + 1)
    try:
        yield
    finally:
        _attack_display_depth.reset(token)


def compact_attack_list_lines(attack_list) -> str:
    return "\n".join(f"**{atk.name}**" for atk in sorted(attack_list.attacks, key=lambda a: a.name))
