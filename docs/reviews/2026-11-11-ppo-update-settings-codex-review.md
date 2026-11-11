# Codex review: ppo-update-settings

- Date: 2026-11-11
- Target: 5415acab856e37fa3f73cea59f247e840c1a5686..feeefd2a064d3bbb94ac7317ce923e2a46753661
- Verdict: needs-attention

## Summary

Found one reproducible backward-compatibility regression. Reviewed the diff and reproduced the validation failure; the full test suite was not run.

## Findings

### 1. [medium] Existing PPO runs can no longer resume

- File: src/quack_rl/rl/experiment.py:96-99
- Confidence: 1.0

Saved configs from before this change lack the three new nested update settings. `_resume_problems()` validates those configs using ExperimentConfig, so resuming an existing run now raises ValidationError for missing n_steps, even with the updated experiment JSON. This also blocks completed-run resume checks and makes the old-CSV migration unreachable for actual legacy runs. The new compatibility test only removes the CSV column while retaining a newly generated config, so it misses this failure.

Recommendation: Normalize legacy saved configs before resume validation, using their recorded top-level n_steps and batch_size and the historical target_kl=None. Keep explicit fields mandatory for new experiment configs. Add a resume test with a genuine pre-change saved config.

Decision: partly taken - the failure is real (a run directory saved before #319 cannot be resumed, which also leaves the old-CSV path of #320 unreachable for real old runs), but no run in use needs it: S0-S5 are finished, S6 started fresh, L never started. Per the owner's no-legacy-shims preference no config migration is added now. A follow-up issue (label `later`) to choose between a clear resume error plus removing the unreachable path, or a real migration with a genuine pre-#319 test, was drafted; filing it from the loop session was denied by the auto mode classifier, so the owner files it or decides otherwise.

## Next steps

- Add legacy saved-config migration and verify resume with both the old config and old CSV format.
