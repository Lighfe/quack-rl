from collections import Counter
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic import Field as PydField

from quack_rl.rules.cards import get_card_effect
from quack_rl.rules.spellbook import get_spellbook


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ChipSpec(_Frozen):
    id: str
    colour: str
    value: int = PydField(ge=1)


class ShopItem(_Frozen):
    id: str
    price: int = PydField(ge=0)
    kind: Literal["chip"]
    chip: str
    # `halves` and `points` are only read by the bots (removed with their last reader in #173).
    halves: int = 0
    points: int = 0
    # v1.10: the item can be bought from this round on (rounds are numbered from 1).
    min_round: int = PydField(default=1, ge=1, strict=True)


class DieFace(_Frozen):
    id: str
    weight: int = PydField(ge=1)
    kind: Literal["droplet", "chip", "points", "rubies"]
    chip: str | None = None
    halves: int = 0
    points: int = 0
    rubies: int = 0


DECK_SIZE = 20


class CardSpec(_Frozen):
    id: str
    # The name of a registered card effect (`quack_rl.rules.cards`).
    effect: str
    count: int = PydField(ge=1, strict=True)


class RoundChip(_Frozen):
    """A chip that every player gets into the bag at the start of this round (rounds from 1)."""

    round: int = PydField(strict=True)
    chip: str


class PointBoard(_Frozen):
    """The points board (v2.1): fields 0..fields, `laps` laps, rat tails between some fields.

    A rat tail after field f lies at total f and at total f + fields (on every lap).
    """

    fields: int = PydField(ge=1, strict=True)
    rat_tails: list[Annotated[int, PydField(strict=True)]]
    laps: int = PydField(default=2, ge=1, strict=True)

    @property
    def max_points(self) -> int:
        return self.fields * self.laps

    @model_validator(mode="after")
    def _check_tails(self) -> "PointBoard":
        if any(not 0 <= t <= self.fields - 1 for t in self.rat_tails):
            raise ValueError(f"rat_tails: every tail must lie in 0..{self.fields - 1}")
        if any(a >= b for a, b in zip(self.rat_tails, self.rat_tails[1:])):
            raise ValueError("rat_tails: must be strictly increasing")
        return self


def _check_kind_fields(entry: "ShopItem | DieFace") -> None:
    needed = {
        "droplet": "halves",
        "points": "points",
        "rubies": "rubies",
    }.get(entry.kind)
    if needed is not None and getattr(entry, needed, 1) < 1:
        raise ValueError(f"{entry.id}: kind {entry.kind} needs {needed} of at least 1")
    if entry.kind == "chip" and entry.chip is None:
        raise ValueError(f"{entry.id}: kind {entry.kind} needs a chip")


def _check_unique_ids(name: str, ids: list[str]) -> None:
    duplicates = sorted(i for i, n in Counter(ids).items() if n > 1)
    if duplicates:
        raise ValueError(f"{name}: duplicate ids {duplicates}")


class Field(_Frozen):
    """One pot field: the money and the points it gives, and whether it is a ruby field."""

    money: int = PydField(ge=0)
    points: int = PydField(ge=0)
    ruby: bool


class Ruleset(_Frozen):
    version: str
    rounds: int = PydField(ge=1)
    explosion_limit: int = PydField(ge=1)
    # Shop limits per player per round; `max_chip_purchases` None means no limit.
    max_chip_purchases: int | None = PydField(default=None, ge=0)
    distinct_chip_colours: bool = False
    track_end: int = PydField(ge=1)
    # One entry per pot field 0..track_end: money, points and the ruby marker.
    fields: list[Field]
    # An exploded player chooses the money or the points of the scoring field. Always on in v2.
    explosion_choice: Literal[True]
    # In the last round, money // this becomes points.
    last_round_money_divisor: int = PydField(ge=1)
    # At game end (after the last round, which has no shop), rubies // this become points.
    last_round_ruby_divisor: int = PydField(ge=1, strict=True)
    # Rubies are a currency: every player starts with `start_rubies`; `ruby_cost` rubies buy a droplet +1.
    start_rubies: int = PydField(ge=0)
    ruby_cost: int = PydField(ge=1)
    # The ruby step: rubies are spent (ruby_drop, refill_flask) in their own step after the shop,
    # not in the shop. False (v2.1): the shop offers the ruby spends among the chip buys.
    ruby_step: bool = PydField(default=False, strict=True)
    # The name of the spellbook that gives each colour its component.
    spellbook: int | str
    # The deck of round-start cards.
    cards: list[CardSpec] = PydField(min_length=1)
    # The points board with rat tails.
    point_board: PointBoard
    # Chips every player gets into the bag at the card step of a round (default: none).
    round_chips: list[RoundChip] = PydField(default_factory=list)
    start_bag: dict[str, Annotated[int, PydField(ge=1)]]
    chips: list[ChipSpec]
    shop: list[ShopItem]
    die: list[DieFace]

    @model_validator(mode="after")
    def _check_references(self) -> "Ruleset":
        _check_unique_ids("chips", [c.id for c in self.chips])
        _check_unique_ids("shop", [i.id for i in self.shop])
        _check_unique_ids("die", [f.id for f in self.die])
        _check_unique_ids("cards", [c.id for c in self.cards])
        for card in self.cards:
            get_card_effect(card.effect)  # raises for an unregistered effect name
        if sum(c.count for c in self.cards) < self.rounds:
            raise ValueError(
                f"the deck has {sum(c.count for c in self.cards)} cards, fewer than the "
                f"{self.rounds} rounds: one card is drawn per round"
            )
        deck = {c.id: c.count for c in self.cards}
        if deck != {f"card_{n}": 1 for n in range(1, DECK_SIZE + 1)}:
            raise ValueError(
                f"cards: the deck is the {DECK_SIZE} cards card_1 to card_{DECK_SIZE}, one of each"
            )
        for entry in [*self.shop, *self.die]:
            _check_kind_fields(entry)
        self._check_components()
        chip_ids = {c.id for c in self.chips}
        if len(self.fields) != self.track_end + 1:
            raise ValueError("fields needs one entry per field 0..track_end")
        for chip_id in self.start_bag:
            if chip_id not in chip_ids:
                raise ValueError(f"start_bag: unknown chip {chip_id}")
        for entry in [*self.shop, *self.die]:
            if entry.kind == "chip" and entry.chip not in chip_ids:
                raise ValueError(f"{entry.id}: unknown chip {entry.chip}")
        for rc in self.round_chips:
            if not 1 <= rc.round <= self.rounds:
                raise ValueError(
                    f"round_chips: round {rc.round} is not between 1 and {self.rounds}"
                )
            if rc.chip not in chip_ids:
                raise ValueError(f"round_chips: unknown chip {rc.chip}")
        return self

    def _check_components(self) -> None:
        book = get_spellbook(self.spellbook)  # raises for an unregistered name
        for c in self.chips:
            if c.colour not in book:
                raise ValueError(
                    f"chip {c.id}: spellbook {self.spellbook!r} has no colour {c.colour!r}"
                )

    def component_name(self, chip: ChipSpec) -> str:
        """The component name of a chip: the spellbook gives one for each colour."""
        return get_spellbook(self.spellbook)[chip.colour]

    def chip(self, chip_id: str) -> ChipSpec:
        for c in self.chips:
            if c.id == chip_id:
                return c
        raise KeyError(chip_id)

    def card(self, card_id: str) -> CardSpec:
        for c in self.cards:
            if c.id == card_id:
                return c
        raise KeyError(card_id)

    def shop_item(self, item_id: str) -> ShopItem:
        for item in self.shop:
            if item.id == item_id:
                return item
        raise KeyError(item_id)
