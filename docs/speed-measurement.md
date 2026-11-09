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

Spec values (`archive/docs/specs/2026-10-09-m2-1-bots-and-balance.md`, "Tournament"), random bots: 5.4 ms and 21.5 KB per game, about 0.9 KB gzipped.

- `bot:random`: 4.92 ms (9% faster than the spec, inside the 30% threshold), 21.55 KB raw (same). Gzipped: 1.65 KB, 83% above the spec value, so this row differs by more than 30%. Likely reason: this script compresses each game on its own, so the compressor has no repeated content from earlier games; the spec's 0.9 KB was most likely taken from a shard of many games compressed together.
- Heuristic bots: 10.17 to 12.24 ms per game, which is 1.9 to 2.3 times slower than the spec's 5.4 ms (2.1 to 2.5 times slower than the `bot:random` row here). Records are 2.0 to 2.4 times larger raw (43.1 to 52.4 KB) and 1.5 to 1.6 times larger gzipped per game.
- The tournament mixes bots and writes no records, so its 8.3 ms per game (1 / 120.9 games/s) is below the per-bot average of 9.7 ms.

## Env step, 2026-11

Measured on 2026-11-09 for issue #310 (faster `QuackEnv.step`, games unchanged).

Machine: Intel(R) Core(TM) i7-8650U CPU @ 1.90GHz, 8 cores (4 physical cores, 8 threads).

Before is the trace commit `d74bb17` (the env trace and `tests/test_env_trace.py` only, no change under `src/`). After is the final commit of the issue; its code is the code of `67f7848`. `tests/test_env_trace.py::test_env_trace_unchanged` passes on both, so every observation, mask, reward, flag and episode summary of the trace is the same.

Command (agent seat p1, opponent `bot:topchip-draw20-pts6`, random legal agent actions, seed 0):

```
uv run python scripts/measure_speed.py --env-steps 20000
```

| run | before (steps/s) | after (steps/s) |
|---:|---:|---:|
| 1 | 159.1 | 1962.1 |
| 2 | 162.6 | 1918.4 |

Speed-up: about 12 times (mean 160.9 before, 1940.3 after).

What changed:

- `QuackEnv` built the observation vector and the mask of both seats through `QuackParallelEnv._obs` after every parallel-env step, only to check whether the agent's mask was Wait-only, and once more for the returned observation: about 5.8 `_obs` calls (11.6 vectors and masks) per agent step. It now reads only the agent's mask between parallel steps (`QuackParallelEnv._step_seat`, `_mask`) and builds the agent's observation vector once per agent step (`_vector`). `QuackParallelEnv.step` and `reset` still return both seats' observations as before.
- `action_mask` called `action_names(rs)` for every mask; it now uses a cached name-to-index table of the ruleset.
- The per-ruleset helpers of the encoder (`_colours`, `_card_kinds`, `has_hand`, the derived names) are cached per ruleset object.

Profile command:

```
uv run python -m cProfile -s cumulative scripts/measure_speed.py --env-steps 20000
```

The profiler slows the run (90.5 steps/s before, 1020.3 after under `cProfile`). Top 15 lines by cumulative time, before (481,278,076 function calls in 221.4 s):

```
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
    745/1    0.029    0.000  221.464  221.464 {built-in method builtins.exec}
        1    0.000    0.000  221.464  221.464 measure_speed.py:1(<module>)
        1    0.000    0.000  221.013  221.013 measure_speed.py:109(main)
        1    0.439    0.439  221.011  221.011 measure_speed.py:79(env_steps_per_second)
    20000    0.087    0.000  217.575    0.011 single_env.py:161(step)
   116130    1.907    0.000  211.281    0.002 parallel_env.py:80(_obs)
    20007    0.351    0.000  181.057    0.009 single_env.py:91(_advance)
    47642    0.232    0.000   92.448    0.002 parallel_env.py:102(step)
   232260    2.266    0.000   83.839    0.000 encode.py:472(action_mask)
   232261    4.501    0.000   79.170    0.000 actions.py:73(action_names)
   232260    4.282    0.000   69.902    0.000 encode.py:363(vectorize)
   232260    7.039    0.000   55.633    0.000 encode.py:163(observe)
  7432352    9.833    0.000   46.479    0.000 actions.py:66(_appended)
  9526447   25.891    0.000   41.414    0.000 {built-in method fromkeys}
    20419    0.047    0.000   37.119    0.002 single_env.py:114(_observation)
```

After (28,783,612 function calls in 20.0 s):

```
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
    745/1    0.030    0.000   20.073   20.073 {built-in method builtins.exec}
        1    0.000    0.000   20.073   20.073 measure_speed.py:1(<module>)
        1    0.000    0.000   19.615   19.615 measure_speed.py:109(main)
        1    0.348    0.348   19.613   19.613 measure_speed.py:79(env_steps_per_second)
    20000    0.066    0.000   18.071    0.001 single_env.py:158(step)
    21257    0.140    0.000    9.869    0.000 parallel_env.py:84(_vector)
    20419    0.032    0.000    9.838    0.000 single_env.py:111(_observation)
    20007    0.207    0.000    8.301    0.000 single_env.py:91(_advance)
    21257    0.378    0.000    5.291    0.000 encode.py:394(vectorize)
    47642    0.037    0.000    5.038    0.000 parallel_env.py:132(_step_seat)
    47642    0.130    0.000    4.991    0.000 parallel_env.py:123(_play)
    55176    0.480    0.000    4.796    0.000 game.py:47(step)
    21257    0.652    0.000    4.438    0.000 encode.py:194(observe)
    47642    0.108    0.000    2.075    0.000 single_env.py:86(_opponent_action)
    21257    1.314    0.000    1.884    0.000 encode.py:379(_map_values)
```

After the change the time is spread over building the one observation (`observe` and `vectorize`, about half of the step), the engine step and the opponent bot; no single function dominates.
