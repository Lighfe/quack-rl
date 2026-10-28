# Archive

Code and data from before ruleset v2 and the old training stack: the marimo notebooks (`notebooks/`), their tests (`tests/`) and the old analysis notes with their run data (`docs/analysis/`).

The files are moved, not deleted, so they can be recycled later. Nothing imports, tests or checks them, and they are not maintained.

It also holds the old training stack (`src/`, `scripts/`, `tests/`): the trainers, self-play, the offline and replay code, the dataset builder, the evaluator and the `policy:` seat (`PolicyBot`), with the tests of each. Each file keeps its old path below `archive/`, so it could be recycled. It is moved, not deleted, and nothing imports, tests or checks it. Part of it is ported to ruleset v2.1 (issues #194 to #196); the table below says which.

## Training stack: ported and not ported

Ported (old path -> new path):

| Old path | New path |
|---|---|
| `archive/src/quack_rl/rl/train.py` | `src/quack_rl/rl/train.py` |
| `archive/src/quack_rl/rl/selfplay.py` | `src/quack_rl/rl/selfplay.py` |
| `archive/src/quack_rl/rl/dataset.py` | `src/quack_rl/rl/dataset.py` |
| `archive/src/quack_rl/rl/offline.py` | `src/quack_rl/rl/offline.py` |
| `archive/src/quack_rl/rl/evaluate.py` | `src/quack_rl/rl/evaluate.py` |
| `archive/src/quack_rl/rl/policy_bot.py` | `src/quack_rl/rl/policy_bot.py` |
| `archive/src/quack_rl/rl/derive.py` | `src/quack_rl/rl/derive.py` |
| `archive/src/quack_rl/rl/encode.py` | `src/quack_rl/rl/encode.py` |
| `archive/scripts/train.py` | `scripts/train_ppo.py` |
| `archive/scripts/train_selfplay.py` | `scripts/train_selfplay.py` |
| `archive/scripts/build_dataset.py` | `scripts/build_dataset.py` |
| `archive/scripts/train_offline.py` | `scripts/train_offline.py` |

Not ported: `archive/src/quack_rl/rl/finetune.py`, `replay_dqn.py`, `runs.py`, `policy_layout.py`, the layout 7 files (`derive_layout7.py`, `encode_layout7.py`), and the archived tests of the ported files (the new tests are in `tests/test_rl_*.py`).

## Ruleset v2

Ruleset v2 was renamed to `v2.1` (issue #180), which has exactly its numbers. The v2 files are kept here with their old path below `archive/`:

- `archive/src/quack_rl/rules/v2.toml`: the ruleset file
- `archive/docs/rules/rules-v2.md`: the rules text
- `archive/tests/test_golden_v2.py`, `archive/tests/fixtures/golden/v2_random_seed7.jsonl` and `archive/tests/fixtures/golden/v2_bots_results.csv`: the golden replay of v2 with its stored game and bots results
- `archive/tests/fixtures/make_golden.py`: the generator of those fixtures (the live copy `tests/fixtures/make_golden.py` makes the `v2.1` fixtures)

`v2` is not a known ruleset name any more: `load_ruleset("v2")` and `--rules v2` fail.

## Rulesets v2.1 and v2.2

Ruleset v2.3 replaced both (issue #243): its black chip gives droplet +1 and 1 ruby to the larger count (not 3 rubies), the droplet counts whole steps everywhere (no `droplet_halves`, no `halves` in events), the ruby step after the shop is the rule (no `ruby_step` field), and the record schema version is 3. The v2.1 and v2.2 files keep their old path below `archive/`:

- `archive/src/quack_rl/rules/v2.1.toml`, `v2.2.toml`: the ruleset files
- `archive/docs/rules/rules-v2.1.md`, `rules-v2.2.md`: the rules texts
- `archive/tests/fixtures/golden/v2_1_random_seed7.jsonl`, `v2_2_random_seed7.jsonl`, `v2_1_bots_results.csv` and `layout8_sample.json`: the golden records, the bots results and the observation layout 8 sample
- `archive/tests/test_golden_v2_1.py`, `test_golden_v2_2.py`, `test_ruleset_v2_1.py`, `test_ruleset_v2_2.py`: the per-version tests
- `archive/tests/test_ruby_step_v2_2.py`, `test_bots_v2_2.py`: the v2.2 forms of the ruby step tests, with the checks that compared v2.2 with v2.1 (the live ports are `tests/test_ruby_step.py` and `tests/test_bots_ruby_step.py`)

`v2.1` and `v2.2` are not known ruleset names any more, and their records (schema version 2) are not read.
