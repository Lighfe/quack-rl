"""One game of the web service: the engine state, the seats, the pending actions and the log.

The session only calls the engine. It steps through the phases that take no actions, through
seats whose only legal action is `wait` and through bot decisions, until a human must act or
the game is over.
"""

import secrets
import threading
from collections.abc import Mapping
from typing import Any

from quack_rl.cli.seats import check_seat, parse_seat
from quack_rl.engine import (
    SEATS,
    WAIT,
    ChanceSource,
    GameState,
    Phase,
    RngChance,
    legal_actions,
    needs_actions,
    new_game,
    start_field,
    step,
)
from quack_rl.rules import Ruleset
from quack_rl.runner import Seat

HUMAN = "human"
HIDDEN_KINDS = ("hand", "put_back")  # events that only the acting seat may see


class StaleRevision(Exception):
    """The action was sent for an old revision, or the seat already acted on this one."""


class IllegalSubmit(Exception):
    """The action is not legal for the seat now (none is legal after the game is over)."""

    def __init__(self, legal: list[str]):
        super().__init__(f"legal: {legal}")
        self.legal = legal


class GameSession:
    def __init__(
        self,
        rs: Ruleset,
        seats: Mapping[str, Seat | None],
        chance: ChanceSource,
    ):
        self.rs = rs
        self.seats = dict(seats)  # None is a human seat
        self.chance = chance
        self.state: GameState = new_game(rs)
        self.pending: dict[str, str] = {}
        self.events: list[dict[str, Any]] = []
        self._froms: dict[str, list[int]] = {seat: [] for seat in SEATS}
        # The bonus die of the newest resolve: its round and its `die` events (seat, face), in
        # event order; None before the first resolve. Die rolls of other steps do not change it.
        self.last_roll: dict[str, Any] | None = None
        self.lock = threading.Lock()

    @classmethod
    def create(cls, rs: Ruleset, specs: Mapping[str, str], seed: int | None) -> "GameSession":
        """Seat specs as in `quack-rl play`; raises `typer.BadParameter` for an unknown spec.
        The bot seeds follow `quack-rl play`: 2 * seed + 1 for p1, 2 * seed + 2 for p2."""
        for spec in specs.values():
            check_seat(spec, allow_human=True)
        game_seed = seed if seed is not None else secrets.randbelow(2**31)
        seats: dict[str, Seat | None] = {}
        for i, seat in enumerate(SEATS, start=1):
            spec = specs[seat]
            seats[seat] = None if spec == HUMAN else parse_seat(spec, 2 * game_seed + i, rs=rs)
        session = cls(rs, seats, RngChance(game_seed))
        session.advance()
        return session

    @property
    def revision(self) -> int:
        return self.state.step

    def kind(self, seat: str) -> str:
        bot = self.seats[seat]
        return HUMAN if bot is None else bot.name

    def to_act(self) -> list[str]:
        if not needs_actions(self.state):
            return []
        return [seat for seat in SEATS if seat not in self.pending]

    def legal(self, seat: str) -> list[str]:
        """The legal actions of `seat`; none after the game is over."""
        if self.state.phase is Phase.GAME_OVER:
            return []
        return legal_actions(self.state, self.rs, seat)

    def submit(self, seat: str, action: str, revision: int) -> None:
        if self.state.phase is Phase.GAME_OVER:
            raise IllegalSubmit([])
        if revision != self.revision or seat not in self.to_act():
            raise StaleRevision()
        legal = self.legal(seat)
        if action not in legal:
            raise IllegalSubmit(legal)
        self.pending[seat] = action
        self.advance()

    def advance(self) -> None:
        while self.state.phase is not Phase.GAME_OVER:
            if not needs_actions(self.state):
                self._step(None)
                continue
            for seat in SEATS:
                if seat in self.pending:
                    continue
                legal = legal_actions(self.state, self.rs, seat)
                bot = self.seats[seat]
                if legal == [WAIT]:
                    self.pending[seat] = WAIT
                elif bot is not None:
                    self.pending[seat] = bot.choose(self.state, seat, legal)
            if len(self.pending) < len(SEATS):
                return
            actions, self.pending = self.pending, {}
            self._step(actions)

    def _step(self, actions: dict[str, str] | None) -> None:
        result = step(self.state, self.rs, actions, self.chance)
        self.state = result.state
        for event in result.events:
            self.events.append(event)
            self._track_pot(event)
        if result.phase is Phase.RESOLVE:
            self.last_roll = {
                "round": result.round,
                "rolls": [
                    {"seat": e["seat"], "face": e["face"]}
                    for e in result.events
                    if e["kind"] == "die"
                ],
            }

    def _track_pot(self, event: dict[str, Any]) -> None:
        """The first field of each chip in the pot, from the `place` events."""
        kind, seat = event["kind"], event.get("seat")
        if kind == "round_end":
            for froms in self._froms.values():
                froms.clear()
            return
        if seat not in self._froms:
            return
        froms = self._froms[seat]
        if kind == "place":
            froms.append(min(event["from"] + 1, self.rs.track_end))
        elif kind == "pot_put_back" and len(froms) >= 2:
            froms.pop(-2)
        elif kind in ("use_flask", "use_card_17") and froms:
            froms.pop()
        elif kind == "restart":
            froms.clear()

    def pot_froms(self, seat: str) -> list[int]:
        """The first field of each chip in the pot of `seat`, in placement order. When the state
        was set from outside (tests), the chips without a `place` event start after the landing
        field of the chip before."""
        p = self.state.players[seat]
        froms = self._froms[seat]
        if len(froms) != len(p.placed):
            previous = [start_field(p, self.rs), *p.placed_fields[:-1]]
            froms[:] = [min(f + 1, self.rs.track_end) for f in previous]
        return list(froms)

    def events_for(self, seat: str) -> list[dict[str, Any]]:
        """The log of `seat`: every event except another seat's hand events."""
        return [
            e
            for e in self.events
            if not (e["kind"] in HIDDEN_KINDS and e.get("seat") not in (None, seat))
        ]
