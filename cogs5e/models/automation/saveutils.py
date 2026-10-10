from utils.constants import SAVE_BONUS_PATTERN, normalize_save_bonus_token


def parse_save_bonuses(save_type: str, save_bonuses: list[str]) -> list[str]:
    """
    Parse a save bonus string.
    """
    out = []
    for save_bonus_combo in save_bonuses:
        current_out = []
        for match_text in SAVE_BONUS_PATTERN.split(save_bonus_combo):
            if not match_text:
                continue
            save_bonus = normalize_save_bonus_token(match_text)
            if not save_bonus:
                continue
            if "|" not in save_bonus:
                out.append(save_bonus)
                continue
            save_bonus_dice, bonus_save_type = save_bonus.split("|", 1)
            bonus_save_type = bonus_save_type[:3]

            if bonus_save_type == save_type:
                current_out.append(save_bonus_dice)
        if current_out:
            out.append("+".join(current_out))

    return out
