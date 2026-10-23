# Archive

Code and data from before ruleset v2 and the old training stack: the marimo notebooks (`notebooks/`), their tests (`tests/`) and the old analysis notes with their run data (`docs/analysis/`).

The files are moved, not deleted, so they can be recycled later. Nothing imports, tests or checks them, and they are not maintained.

It also holds the old training stack (`src/`, `scripts/`, `tests/`): the trainers, self-play, the offline and replay code, the dataset builder, the evaluator and the `policy:` seat (`PolicyBot`), with the tests of each. Each file keeps its old path below `archive/`, so it can be recycled when training is rebuilt on ruleset v2.1. It is moved, not deleted, and nothing imports, tests or checks it.

## Ruleset v2

Ruleset v2 was renamed to `v2.1` (issue #180), which has exactly its numbers. The v2 files are kept here with their old path below `archive/`:

- `archive/src/quack_rl/rules/v2.toml`: the ruleset file
- `archive/docs/rules/rules-v2.md`: the rules text
- `archive/tests/test_golden_v2.py`, `archive/tests/fixtures/golden/v2_random_seed7.jsonl` and `archive/tests/fixtures/golden/v2_bots_results.csv`: the golden replay of v2 with its stored game and bots results
- `archive/tests/fixtures/make_golden.py`: the generator of those fixtures (the live copy `tests/fixtures/make_golden.py` makes the `v2.1` fixtures)

`v2` is not a known ruleset name any more: `load_ruleset("v2")` and `--rules v2` fail.
