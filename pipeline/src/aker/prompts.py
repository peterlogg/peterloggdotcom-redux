"""Shared description of the aker, given to both extractors."""
from aker.config import PEOPLE

AKER_CONTEXT = (
    "This is one Friday evening + Saturday of a WhatsApp group chat between four friends: "
    f"{', '.join(PEOPLE)}. During the football season they run a weekly accumulator ('acca'/'aker'): "
    "on Saturday each person names one team playing a 3pm kick-off, implicitly backing that team to win. "
    "Occasionally the pick is a different market (e.g. over 2.5 goals). One person places the £20 bet, rotating weekly. "
    "Teams are often called by nicknames (Gers, Hibs, Accies, Boro, Spurs, Man U...). "
    "People sometimes change picks; the last stated pick counts. Ignore teams mentioned only in banter, "
    "other bets, or results chat."
)
