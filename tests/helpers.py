from quack_rl.engine import ScriptedChance, new_game, step
from quack_rl.rules import load_ruleset

RS = load_ruleset("v2")


def play(state, p1, p2, *chance):
    """One joint step with scripted chance outcomes (chip ids or die face ids, in order)."""
    return step(state, RS, {"p1": p1, "p2": p2}, ScriptedChance(chance))


def auto(state, *chance):
    """One step without actions (Resolve)."""
    return step(state, RS, None, ScriptedChance(chance))


def brew_start(rs=RS):
    """A new game after the first card (a card without effect), at the first brew step."""
    return step(new_game(rs), rs, None, ScriptedChance(["card_8_to_12"])).state
