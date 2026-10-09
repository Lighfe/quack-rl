from quack_rl.engine import ScriptedChance, step
from quack_rl.rules import load_ruleset

RS = load_ruleset("v1")


def play(state, p1, p2, *chance):
    """One joint step with scripted chance outcomes (chip ids or die face ids, in order)."""
    return step(state, RS, {"p1": p1, "p2": p2}, ScriptedChance(chance))


def auto(state, *chance):
    """One step without actions (Resolve)."""
    return step(state, RS, None, ScriptedChance(chance))
