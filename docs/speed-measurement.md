# Speed measurement of the heuristic bots and the tournament

Measured on 2026-10-10. Numbers differ per machine.

## Machine

- CPU: Intel(R) Core(TM) i7-8650U CPU @ 1.90GHz
- Cores: 8 (4 physical cores, 8 threads)

## Commands

Per-bot speed, one core, 1,000 games per bot (both seats the same bot, ruleset `v1`, 9 rounds, game recorded in memory as `simulate` does, seed 0):

```
uv run python scripts/measure_speed.py --games 1000
```

Tournament speed, the same five-bot field, 1,000 games per pairing, same seed, no `--keep-records`:

```
B=bot:random,bot:draw30-pts3-blue,bot:draw30-pts3-green,bot:draw30-pts3-cleaner,bot:draw30-pts3-balanced
uv run quack-rl tournament --bots $B --games 1000 --seed 0 --workers 1 --name speed1
uv run quack-rl tournament --bots $B --games 1000 --seed 0 --workers 4 --name speed4
```

## Results

Per bot (`scripts/measure_speed.py`). KB are 1000 bytes; gzip is applied to each game's record alone.

| bot | ms/game | KB/game raw | KB/game gzipped |
|---|---:|---:|---:|
| bot:random | 4.92 | 21.55 | 1.65 |
| bot:draw30-pts3-blue | 10.17 | 43.42 | 2.51 |
| bot:draw30-pts3-green | 10.51 | 43.09 | 2.47 |
| bot:draw30-pts3-cleaner | 12.24 | 52.44 | 2.68 |
| bot:draw30-pts3-balanced | 10.53 | 44.22 | 2.52 |

Tournament: 5 bots give 10 pairings, 1,000 games each, 10,000 games per run. Wall-clock time is measured with `/usr/bin/time` around the whole command, so it includes the start of `uv run` and the rebuild of the 20 sampled games.

| workers | wall clock | games/s |
|---:|---:|---:|
| 1 | 82.71 s | 120.9 |
| 4 | 32.69 s | 305.9 |

Speed-up: 82.71 / 32.69 = 2.53 (4 workers are 2.53 times faster than 1; the machine has 4 physical cores, and the 10 pairings do not split evenly over 4 workers).

## Estimate for 120,000 games

From the tournament runs (mixed field, no records):

- 1 worker: 120,000 / 120.9 games/s = 993 s, about 16.5 minutes
- 4 workers: 120,000 / 305.9 games/s = 392 s, about 6.5 minutes

## Comparison with the spec

Spec values (`docs/specs/2026-10-09-m2-1-bots-and-balance.md`, "Tournament"), random bots: 5.4 ms and 21.5 KB per game, about 0.9 KB gzipped.

- `bot:random`: 4.92 ms (9% faster than the spec, inside the 30% threshold), 21.55 KB raw (same). Gzipped: 1.65 KB, 83% above the spec value, so this row differs by more than 30%. Likely reason: this script compresses each game on its own, so the compressor has no repeated content from earlier games; the spec's 0.9 KB was most likely taken from a shard of many games compressed together.
- Heuristic bots: 10.17 to 12.24 ms per game, which is 1.9 to 2.3 times slower than the spec's 5.4 ms (2.1 to 2.5 times slower than the `bot:random` row here). Records are 2.0 to 2.4 times larger raw (43.1 to 52.4 KB) and 1.5 to 1.6 times larger gzipped per game.
- The tournament mixes bots and writes no records, so its 8.3 ms per game (1 / 120.9 games/s) is below the per-bot average of 9.7 ms.
