from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ChipSpec(_Frozen):
    id: str
    colour: str
    value: int
    component: str


class ShopItem(_Frozen):
    id: str
    price: int
    kind: Literal["chip", "remove_chip", "droplet", "points"]
    chip: str | None = None
    halves: int = 0
    points: int = 0


class DieFace(_Frozen):
    id: str
    weight: int
    kind: Literal["droplet", "chip", "money", "points"]
    chip: str | None = None
    halves: int = 0
    amount: int = 0
    points: int = 0


def _check_unique_ids(name: str, ids: list[str]) -> None:
    duplicates = sorted(i for i, n in Counter(ids).items() if n > 1)
    if duplicates:
        raise ValueError(f"{name}: duplicate ids {duplicates}")


class Ruleset(_Frozen):
    version: str
    rounds: int
    explosion_limit: int
    max_purchases: int
    track_end: int
    money: list[int]
    rubies: list[int]
    start_bag: dict[str, int]
    chips: list[ChipSpec]
    shop: list[ShopItem]
    die: list[DieFace]

    @model_validator(mode="after")
    def _check_references(self) -> "Ruleset":
        _check_unique_ids("chips", [c.id for c in self.chips])
        _check_unique_ids("shop", [i.id for i in self.shop])
        _check_unique_ids("die", [f.id for f in self.die])
        chip_ids = {c.id for c in self.chips}
        if len(self.money) != self.track_end + 1:
            raise ValueError("money needs one entry per field 0..track_end")
        if any(not 0 <= f <= self.track_end for f in self.rubies):
            raise ValueError("ruby field outside the track")
        for chip_id in self.start_bag:
            if chip_id not in chip_ids:
                raise ValueError(f"start_bag: unknown chip {chip_id}")
        for entry in [*self.shop, *self.die]:
            if entry.kind in ("chip", "remove_chip") and entry.chip not in chip_ids:
                raise ValueError(f"{entry.id}: unknown chip {entry.chip}")
        return self

    def chip(self, chip_id: str) -> ChipSpec:
        for c in self.chips:
            if c.id == chip_id:
                return c
        raise KeyError(chip_id)

    def shop_item(self, item_id: str) -> ShopItem:
        for item in self.shop:
            if item.id == item_id:
                return item
        raise KeyError(item_id)
