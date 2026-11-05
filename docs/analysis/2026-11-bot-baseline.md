# Bot baseline tournament (November 2026)

Issue: #271. Spec: `docs/specs/2026-11-05-rule-bots-and-rl-proof.md` ("Offered bots").

The tournament plays all 18 rule bot settings and `bot:random` against each other, to pick one
preset bot per strategy (`PRESET_BOTS` in `src/quack_rl/bots/presets.py`).

## Run

```
uv run quack-rl tournament --field full --games 200 --seed 271 --name bot-baseline
```

- Ruleset v2.3, 9 rounds (the defaults), no overrides
- 19 seats, 171 pairings, 200 games per pairing: 34,200 games, 3,600 games per seat
- In each pairing the seat that comes first in the field is p1, so `bot:random` is always p2
- The original run used `--workers 4`; the worker count does not change the results
- 50 of the 34,200 games were draws

To repeat it, add `--out <folder>` and run `uv run quack-rl report <folder>/<run folder>`. The
Ranking section must show the win rates below.

## Ranking

As printed in the "Ranking" section of `quack-rl report` on the run folder. A draw counts as half a
win; the interval is the 95% Wilson interval.

| bot | games | win rate | 95% interval | avg points |
|---|---:|---:|---|---:|
| blackpurple-draw20-pts6 | 3600 | 68.0% | 66.5-69.5% | 52.7 |
| blackpurple-draw20-pts4 | 3600 | 63.3% | 61.7-64.9% | 51.9 |
| blackpurple-draw40-pts6 | 3600 | 60.1% | 58.5-61.7% | 50.1 |
| topchip-draw20-pts6 | 3600 | 60.1% | 58.5-61.7% | 50.8 |
| spendmost-draw20-pts6 | 3600 | 60.0% | 58.4-61.6% | 51.2 |
| spendmost-draw20-pts4 | 3600 | 57.5% | 55.9-59.1% | 50.7 |
| topchip-draw20-pts4 | 3600 | 56.2% | 54.5-57.8% | 49.9 |
| blackpurple-draw40-pts4 | 3600 | 54.3% | 52.6-55.9% | 49.5 |
| topchip-draw40-pts6 | 3600 | 53.9% | 52.3-55.5% | 49.4 |
| spendmost-draw40-pts6 | 3600 | 52.7% | 51.0-54.3% | 48.8 |
| blackpurple-draw0-pts4 | 3600 | 50.4% | 48.8-52.0% | 47.9 |
| topchip-draw40-pts4 | 3600 | 49.2% | 47.6-50.9% | 48.6 |
| blackpurple-draw0-pts6 | 3600 | 48.1% | 46.5-49.7% | 47.9 |
| spendmost-draw40-pts4 | 3600 | 47.1% | 45.5-48.7% | 48.3 |
| topchip-draw0-pts4 | 3600 | 42.6% | 41.0-44.2% | 46.1 |
| spendmost-draw0-pts6 | 3600 | 42.4% | 40.8-44.0% | 46.4 |
| topchip-draw0-pts6 | 3600 | 42.1% | 40.5-43.7% | 46.3 |
| spendmost-draw0-pts4 | 3600 | 42.1% | 40.5-43.7% | 46.6 |
| random | 3600 | 0.0% | 0.0-0.1% | 21.0 |

## Picks

The pick per strategy is the seat of that strategy with the highest win rate over all its 3,600
games; on a tie the higher average final points, then the earlier seat in `field_specs("full")`.
No tie came up: the closest race was in `spendmost` (draw20-pts6 at 59.97% against draw20-pts4 at
57.54%).

| strategy | pick | win rate (all games) |
|---|---|---:|
| `topchip` | `bot:topchip-draw20-pts6` | 60.1% |
| `spendmost` | `bot:spendmost-draw20-pts6` | 60.0% |
| `blackpurple` | `bot:blackpurple-draw20-pts6` | 68.0% |

All three picks use a draw limit of 20% explosion chance and score points from round 6. A draw
limit of 0 is the weakest setting for every strategy.

## Picks against `bot:random`

The 200 games of each pick's pairing with `bot:random`, computed from `results.csv` with
`quack_rl.report.wilson` (a draw is half a win).

| pick | wins / games | win rate | 95% Wilson interval |
|---|---:|---:|---|
| `bot:topchip-draw20-pts6` | 200 / 200 | 100.0% | 98.1-100.0% |
| `bot:spendmost-draw20-pts6` | 200 / 200 | 100.0% | 98.1-100.0% |
| `bot:blackpurple-draw20-pts6` | 200 / 200 | 100.0% | 98.1-100.0% |

Each lower bound (98.1%) is above 50%: every preset clearly beats `bot:random`.
