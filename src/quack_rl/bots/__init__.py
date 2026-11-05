from quack_rl.bots.core import explosion_chance
from quack_rl.bots.random_bot import RandomBot
from quack_rl.bots.rule_bot import RuleBot, bot_name, parse_bot_name
from quack_rl.bots.strategy import STRATEGIES, Strategy

__all__ = [
    "STRATEGIES",
    "RandomBot",
    "RuleBot",
    "Strategy",
    "bot_name",
    "explosion_chance",
    "parse_bot_name",
]
