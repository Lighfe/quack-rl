# Quack RL

A simplified version of The Quacks of Quedlinburg (rules: `docs/rules/rules-v1.md`), built as a recorded game and a reinforcement learning environment. Design: `docs/specs/2026-10-08-quack-rl-design.md`.

## Set-up

Requires [uv](https://docs.astral.sh/uv/).

    uv sync
    uv run quack-rl --help

## Tests

    uv run --with pytest pytest
    HYPOTHESIS_PROFILE=deep uv run --with pytest pytest   # slower, more random games

## Play

    uv run quack-rl play                          # you (p1) vs the random bot
    uv run quack-rl play --p2 human               # hot seat on one keyboard
    uv run quack-rl play --no-bag-assist          # hide the bag contents

Keys: `d` draw, `s` stop, `0` done shopping, `1`-`9`/`a`-`c` buy. Your key is not shown.

## Simulate, replay, verify

    uv run quack-rl simulate --games 1000
    uv run quack-rl replay data/records/v1/play/<file>.jsonl
    uv run quack-rl verify data/records/v1/sim/<run>/shard-0001.jsonl --seed-check

Records go to `data/records/` (not committed).
