import re

from quack_rl.bots import parse_bot_name
from quack_rl.bots.presets import PRESET_BOTS, PRESET_LABELS
from quack_rl.cli.seats import check_seat


def test_presets_are_valid_and_one_per_strategy():
    assert len(PRESET_BOTS) == 3
    for spec in PRESET_BOTS:
        assert spec.startswith("bot:")
        check_seat(spec)
    strategies = [parse_bot_name(spec)[0] for spec in PRESET_BOTS]
    assert strategies == ["topchip", "spendmost", "blackpurple"]
    assert set(PRESET_LABELS) == set(PRESET_BOTS)


def test_labels_name_the_draw_limit_and_points_round_of_their_spec():
    for spec, label in PRESET_LABELS.items():
        _, draw_limit, points_round = parse_bot_name(spec)
        assert re.search(rf"\bdraw {draw_limit} %", label), label
        assert re.search(rf"\bround {points_round}\b", label), label
        assert re.fullmatch(r".+ \(draw \d+ %, points from round \d+\)", label), label
