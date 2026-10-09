import random
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Protocol

from quack_rl.engine.state import PlayerState
from quack_rl.rules import DieFace, Ruleset


class IllegalChance(ValueError):
    """A chance outcome that is not possible in the current state."""


class ChanceSource(Protocol):
    def draw_chip(self, bag: Mapping[str, int], seat: str) -> str: ...

    def roll_die(self, faces: Sequence[DieFace], seat: str) -> str: ...


class RngChance:
    """Seeded chance. Same seed and same calls give the same outcomes."""

    def __init__(self, seed: int):
        self._rng = random.Random(seed)

    def draw_chip(self, bag: Mapping[str, int], seat: str) -> str:
        ids = sorted(c for c, n in bag.items() if n > 0)
        pick = self._rng.randrange(sum(bag[c] for c in ids))
        for chip_id in ids:
            pick -= bag[chip_id]
            if pick < 0:
                return chip_id
        raise IllegalChance("draw from an empty bag")

    def roll_die(self, faces: Sequence[DieFace], seat: str) -> str:
        pick = self._rng.randrange(sum(f.weight for f in faces))
        for face in faces:
            pick -= face.weight
            if pick < 0:
                return face.id
        raise IllegalChance("die without faces")


class ScriptedChance:
    """Chance outcomes given in order (tests)."""

    def __init__(self, values: Iterable[str]):
        self._values = iter(values)

    def _next(self) -> str:
        try:
            return next(self._values)
        except StopIteration:
            raise IllegalChance("scripted chance is exhausted") from None

    def draw_chip(self, bag: Mapping[str, int], seat: str) -> str:
        return self._next()

    def roll_die(self, faces: Sequence[DieFace], seat: str) -> str:
        return self._next()


class ChanceLog:
    """Asks a ChanceSource, validates each outcome against the state, and records it."""

    def __init__(self, source: ChanceSource, rs: Ruleset):
        self.source = source
        self.rs = rs
        self.outcomes: list[dict[str, Any]] = []

    def draw_chip(self, p: PlayerState, seat: str) -> str:
        chip_id = self.source.draw_chip(p.bag, seat)
        if p.bag.get(chip_id, 0) <= 0:
            raise IllegalChance(f"{seat} drew {chip_id}, which is not in the bag")
        self.outcomes.append({"seat": seat, "kind": "draw_chip", "value": chip_id})
        return chip_id

    def roll_die(self, seat: str) -> DieFace:
        face_id = self.source.roll_die(self.rs.die, seat)
        for face in self.rs.die:
            if face.id == face_id:
                self.outcomes.append({"seat": seat, "kind": "die", "value": face_id})
                return face
        raise IllegalChance(f"{seat} rolled {face_id}, which is not a die face")
