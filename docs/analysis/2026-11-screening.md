# Screening (November 2026)

Stage: #309. Spec: `docs/specs/2026-11-09-screening-and-bc-start.md` ("Choice rules", "The
screening record"). Part 1 is the screening of S0, S1 and S2 and the choice of X. Part 2 (S3-S5
and the long run) is #314. The full report is #298. Part 3 (#318) states the shortcomings of
the stage.

The run folders are in `data/experiments/` (git-ignored, not committed); the rows below are
copied from them.

## Part 1: Screening 1 (S0, S1, S2)

Issue: #313. Configs: `experiments/S0.json`, `experiments/S1.json`, `experiments/S2.json` (3 seeds, `steps` 962,560, `checkpoint_every` 96,256, so 10 checkpoints). The runs went one after another on the laptop (8 cores, CPU, 15 GB RAM).

### Commands

S0:

```
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v \
    uv run --group rl python scripts/run_experiment.py \
    --config experiments/S0.json --out data/experiments --threads 1
```

S1:

```
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v \
    uv run --group rl python scripts/run_experiment.py \
    --config experiments/S1.json --out data/experiments --threads 1
```

S2:

```
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v \
    uv run --group rl python scripts/run_experiment.py \
    --config experiments/S2.json --out data/experiments --threads 1
```

S1 again, with `--resume` (see "Run data"):

```
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v \
    uv run --group rl python scripts/run_experiment.py \
    --config experiments/S1.json --out data/experiments --threads 1 --resume
```

### Run data

Wall time, exit status and `Maximum resident set size` are from `/usr/bin/time -v`; start and end are UTC.

| experiment | start | end | wall time | exit status | Maximum resident set size (kB) | `--resume` |
|---|---|---|---|---|---|---|
| S0 | 2026-11-09T18:47:00Z | 2026-11-09T20:59:08Z | 2:12:08 | 0 | 827,204 | no |
| S1 | 2026-11-10T08:00:53Z | 2026-11-10T10:05:48Z | 2:04:54 | 0 | 824,580 | yes |
| S2 | 2026-11-10T10:05:48Z | 2026-11-10T12:11:05Z | 2:05:17 | 0 | 830,380 | no |

S1 first started at 2026-11-09T20:59:08Z. The laptop shut down before its first checkpoint; the seed folders had `config.json` and `ppo.csv` and no checkpoint. The same command with `--resume` (`experiments/README.md`, "Resume after an interruption") restarted each seed from step 0 with the same config, seed and budget, and dropped the `ppo.csv` rows of the first start. The S1 row above is the resumed command.

Planned time per experiment (`experiments/README.md`, "Step budget"): 962,560 / 194.2 + 328 = 5,284.5 s (1:28:05).

Per seed (`done.json` and `config.json`):

| experiment | seed | `steps` in `done.json` | `train_seconds` | `git_commit` |
|---|---|---|---|---|
| S0 | 0 | 962,560 | 7374.8 | `6cebada` |
| S0 | 1 | 962,560 | 7424.2 | `6cebada` |
| S0 | 2 | 962,560 | 7431.7 | `6cebada` |
| S1 | 0 | 962,560 | 7159.2 | `6cebada` |
| S1 | 1 | 962,560 | 7169.3 | `6cebada` |
| S1 | 2 | 962,560 | 7162.8 | `6cebada` |
| S2 | 0 | 962,560 | 7201.7 | `6cebada` |
| S2 | 1 | 962,560 | 7161.6 | `6cebada` |
| S2 | 2 | 962,560 | 7167.2 | `6cebada` |

sha256 of the `final_eval.csv` files:

| file | sha256 |
|---|---|
| `data/experiments/S0/seed0/final_eval.csv` | `e8f758f8a1575dac90a120e09379dc0cbc88edca2b4447872f47e219060f1401` |
| `data/experiments/S0/seed1/final_eval.csv` | `99563717d0120cadbec91dfc6a0d7746067689d694aaf4402435a8ff27b71ae2` |
| `data/experiments/S0/seed2/final_eval.csv` | `56b65d66366536171c4aafc931dab277c19232ecf29eb3f722728a2a9650460d` |
| `data/experiments/S1/seed0/final_eval.csv` | `6856761739d3f70e791a72dc04aa6ac54dc6bf92cb62b99110e29e6aa643d8fb` |
| `data/experiments/S1/seed1/final_eval.csv` | `31ff73fb1fa9b74aea25183a986e6e4abfccd3351bf2e018dbcc8f9e05eb950a` |
| `data/experiments/S1/seed2/final_eval.csv` | `5178fc53fd032d9716a15f1258a6a1f5012a158e0500d8b9e358be4ccbeec6c0` |
| `data/experiments/S2/seed0/final_eval.csv` | `4de2329554f58628609829fb318b1a452c0ae3cc1a718814d70a29c987f7d82c` |
| `data/experiments/S2/seed1/final_eval.csv` | `ca608d27dab61809040d29ddaa4777e2583529e608c697119c8d689eb70f030b` |
| `data/experiments/S2/seed2/final_eval.csv` | `9262a6b55586e01cbf2f2d459408a8ba8ebb160349a9a624b059d087e5125219` |

### Final tables

All rows of the three `final_eval.csv` files of each experiment, copied unchanged (`seed` added from the folder name). The score uses only the `greedy` rows against the three presets; the `bot:random` rows and the `sampled` rows are reported, not scored.

#### S0

| seed | step | opponent | mode | games | wins | draws | losses | win_rate | ci_low | ci_high |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 0 | 1 | 199 | 0.0025 | 0.0002610559935489268 | 0.023490043751831318 |
| 0 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 1 | 1 | 198 | 0.0075 | 0.0017339693431557834 | 0.03182867713845179 |
| 0 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 0 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 0 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 0 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 0 | 962560 | bot:random | greedy | 200 | 183 | 5 | 12 | 0.9275 | 0.8829451897693888 | 0.9559420561780482 |
| 0 | 962560 | bot:random | sampled | 200 | 182 | 3 | 15 | 0.9175 | 0.8710525784724623 | 0.9482115740025201 |
| 1 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 1 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 1 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 1 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 1 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 1 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 1 | 962560 | bot:random | greedy | 200 | 183 | 3 | 14 | 0.9225 | 0.8769783116480144 | 0.9520973875631952 |
| 1 | 962560 | bot:random | sampled | 200 | 175 | 6 | 19 | 0.89 | 0.839073090026985 | 0.926227555398747 |
| 2 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 1 | 2 | 197 | 0.01 | 0.0027466581335444384 | 0.0357217617161768 |
| 2 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 2 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 2 | 0 | 198 | 0.01 | 0.0027466581335444384 | 0.0357217617161768 |
| 2 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 2 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 2 | 962560 | bot:random | greedy | 200 | 193 | 5 | 2 | 0.9775 | 0.9462425386479816 | 0.9907601746617289 |
| 2 | 962560 | bot:random | sampled | 200 | 190 | 5 | 5 | 0.9625 | 0.9262855544509103 | 0.9812825186501182 |

#### S1

| seed | step | opponent | mode | games | wins | draws | losses | win_rate | ci_low | ci_high |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 0 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 0 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 0 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 0 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 0 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 0 | 962560 | bot:random | greedy | 200 | 187 | 8 | 5 | 0.955 | 0.9167032959981803 | 0.976147456998507 |
| 0 | 962560 | bot:random | sampled | 200 | 173 | 12 | 15 | 0.895 | 0.8448196800887696 | 0.9302925120731899 |
| 1 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 1 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 1 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 1 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 1 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 2 | 0 | 198 | 0.01 | 0.0027466581335444384 | 0.0357217617161768 |
| 1 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 1 | 962560 | bot:random | greedy | 200 | 137 | 20 | 43 | 0.735 | 0.6698242380737758 | 0.7913184585289088 |
| 1 | 962560 | bot:random | sampled | 200 | 133 | 18 | 49 | 0.71 | 0.6436252189922268 | 0.7684597439293211 |
| 2 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:random | greedy | 200 | 114 | 18 | 68 | 0.615 | 0.5459986722024608 | 0.6796669027307678 |
| 2 | 962560 | bot:random | sampled | 200 | 119 | 20 | 61 | 0.645 | 0.5765211307549043 | 0.7080137245956883 |

#### S2

| seed | step | opponent | mode | games | wins | draws | losses | win_rate | ci_low | ci_high |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 0 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 0 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 0 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 0 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 0 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 0 | 962560 | bot:random | greedy | 200 | 195 | 3 | 2 | 0.9825 | 0.9532402731826399 | 0.9935739868632978 |
| 0 | 962560 | bot:random | sampled | 200 | 190 | 1 | 9 | 0.9525 | 0.913552896371098 | 0.9743920832574756 |
| 1 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 14 | 1 | 185 | 0.0725 | 0.044057943821951794 | 0.11705481023061112 |
| 1 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 6 | 3 | 191 | 0.0375 | 0.01871748134988186 | 0.07371444554908971 |
| 1 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 6 | 3 | 191 | 0.0375 | 0.01871748134988186 | 0.07371444554908971 |
| 1 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 3 | 1 | 196 | 0.0175 | 0.00642601313670221 | 0.04675972681736004 |
| 1 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 6 | 3 | 191 | 0.0375 | 0.01871748134988186 | 0.07371444554908971 |
| 1 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 6 | 2 | 192 | 0.035 | 0.017055542008567192 | 0.07047061152229073 |
| 1 | 962560 | bot:random | greedy | 200 | 200 | 0 | 0 | 1.0 | 0.9811546736227335 | 1.0 |
| 1 | 962560 | bot:random | sampled | 200 | 199 | 0 | 1 | 0.995 | 0.9722262956021069 | 0.9991168312843989 |
| 2 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 2 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 2 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 2 | 0 | 198 | 0.01 | 0.0027466581335444384 | 0.0357217617161768 |
| 2 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:random | greedy | 200 | 193 | 2 | 5 | 0.97 | 0.9361057075454807 | 0.9861796856598887 |
| 2 | 962560 | bot:random | sampled | 200 | 193 | 2 | 5 | 0.97 | 0.9361057075454807 | 0.9861796856598887 |

### Scores

Score = mean of `win_rate` over the 9 `greedy` rows against `bot:topchip-draw20-pts6`, `bot:spendmost-draw20-pts6` and `bot:blackpurple-draw20-pts6` (3 seeds x 3 presets).

| experiment | score |
|---|---|
| S0 | 0.0036 |
| S1 | 0.0011 |
| S2 | 0.0181 |

The snippet that computed the scores and X (run from the repo root):

```python
import csv
from pathlib import Path

PRESETS = ("bot:topchip-draw20-pts6", "bot:spendmost-draw20-pts6", "bot:blackpurple-draw20-pts6")


def score(exp: str, root: Path = Path("data/experiments")) -> float:
    """Mean greedy final win rate against the three presets over seeds 0, 1, 2 (9 rows)."""
    rates = []
    for seed in (0, 1, 2):
        with open(root / exp / f"seed{seed}" / "final_eval.csv", newline="") as f:
            for row in csv.DictReader(f):
                if row["mode"] == "greedy" and row["opponent"] in PRESETS:
                    rates.append(float(row["win_rate"]))
    assert len(rates) == 9
    return sum(rates) / len(rates)


scores = {exp: score(exp) for exp in ("S0", "S1", "S2")}
M = max(scores.values())
X = next(exp for exp in ("S0", "S1", "S2") if scores[exp] >= M - 0.01)
```

### Learning curves

Per checkpoint `step` of `eval.csv`: the mean of `win_rate` over the 9 `greedy` rows against the three presets (3 seeds x 3 presets, 50 games each).

| step | S0 | S1 | S2 |
|---|---|---|---|
| 96,256 | 0.0078 | 0.0167 | 0.0222 |
| 192,512 | 0.0022 | 0.0100 | 0.0056 |
| 288,768 | 0.0122 | 0.0244 | 0.0222 |
| 385,024 | 0.0244 | 0.0022 | 0.0400 |
| 481,280 | 0.0000 | 0.0133 | 0.0022 |
| 577,536 | 0.0000 | 0.0000 | 0.0144 |
| 673,792 | 0.0067 | 0.0000 | 0.0167 |
| 770,048 | 0.0111 | 0.0056 | 0.0011 |
| 866,304 | 0.0000 | 0.0078 | 0.0156 |
| 962,560 | 0.0000 | 0.0000 | 0.0133 |

### Choice of X

Rule (spec `docs/specs/2026-11-09-screening-and-bc-start.md`, "Choice rules"): M = the highest score; X = the first of S0, S1, S2 whose score is >= M - 0.01 (unrounded scores, the bound counts as within).

```
M        = max(0.0036, 0.0011, 0.0181) = 0.0181
M - 0.01 = 0.0081
S0: 0.0036 < 0.0081  not within
S1: 0.0011 < 0.0081  not within
S2: 0.0181 >= 0.0081  within
```

Unrounded: S0 = 0.0036111111111111114, S1 = 0.0011111111111111111, S2 = 0.018055555555555557, M - 0.01 = 0.008055555555555557.

X: S2

## Part 2: Screening 2 (S3, S4, S5)

Issue: #314. Configs: `experiments/S3.json` (S2 with `init_from_bc` = `data/experiments/B0/seed{seed}/model.pt` and `critic_warmup_steps` 51,200), `experiments/S4.json` and `experiments/S5.json` (S3 with `B1`, `B2` in the path). 3 seeds, `steps` 962,560, `checkpoint_every` 96,256, so 10 checkpoints. PPO seed k starts from the BC model of seed k (paired seeds, #311). The runs went one after another on the laptop (8 cores, CPU, 15 GB RAM).

### Commands

S3:

```
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v \
    uv run --group rl python scripts/run_experiment.py \
    --config experiments/S3.json --out data/experiments --threads 1
```

S4:

```
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v \
    uv run --group rl python scripts/run_experiment.py \
    --config experiments/S4.json --out data/experiments --threads 1
```

S5:

```
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v \
    uv run --group rl python scripts/run_experiment.py \
    --config experiments/S5.json --out data/experiments --threads 1
```

### Run data

Wall time, exit status and `Maximum resident set size` are from `/usr/bin/time -v`; start and end are UTC.

| experiment | start | end | wall time | exit status | Maximum resident set size (kB) | `--resume` |
|---|---|---|---|---|---|---|
| S3 | 2026-11-10T12:50:02Z | 2026-11-10T14:52:57Z | 2:02:54 | 0 | 827,776 | no |
| S4 | 2026-11-10T14:52:57Z | 2026-11-10T16:50:24Z | 1:57:26 | 0 | 832,956 | no |
| S5 | 2026-11-10T16:50:24Z | 2026-11-10T18:47:20Z | 1:56:56 | 0 | 833,608 | no |

Planned time per experiment (`experiments/README.md`, "Step budget"): 962,560 / 194.2 + 328 = 5,284.5 s (1:28:05).

Per seed (`done.json` and `config.json`):

| experiment | seed | `steps` in `done.json` | `train_seconds` | `git_commit` |
|---|---|---|---|---|
| S3 | 0 | 962,560 | 6986.2 | `fc4b843` |
| S3 | 1 | 962,560 | 6968.5 | `fc4b843` |
| S3 | 2 | 962,560 | 6958.6 | `fc4b843` |
| S4 | 0 | 962,560 | 6614.6 | `fc4b843` |
| S4 | 1 | 962,560 | 6657.1 | `fc4b843` |
| S4 | 2 | 962,560 | 6654.1 | `fc4b843` |
| S5 | 0 | 962,560 | 6647.6 | `fc4b843` |
| S5 | 1 | 962,560 | 6685.3 | `fc4b843` |
| S5 | 2 | 962,560 | 6648.8 | `fc4b843` |

BC start per seed (`init_from_bc_path` and `init_from_bc_sha256` in each `config.json`):

| experiment | seed | `init_from_bc_path` | `init_from_bc_sha256` |
|---|---|---|---|
| S3 | 0 | `data/experiments/B0/seed0/model.pt` | `20ed0110b1c07d5d8846806bb77d0f4edb0cc3d9e2e8c4d86e91b4a9602f2292` |
| S3 | 1 | `data/experiments/B0/seed1/model.pt` | `2ee87043528abcf1a546599da3db47e658c0c288c87c8a0af3303888ab005c59` |
| S3 | 2 | `data/experiments/B0/seed2/model.pt` | `a30f1d8d0e5ce3d926feb0b9b025108d26ab64ec54715fdfb4296eced2805d8c` |
| S4 | 0 | `data/experiments/B1/seed0/model.pt` | `9406c52f8ee6271d5edbca49cae44dc7a4a66684e3aec9a5cf8520466ed325a0` |
| S4 | 1 | `data/experiments/B1/seed1/model.pt` | `0b59a1040777e3026d538132ec2626053162dec057ebd2d9a9147fcfc75752ab` |
| S4 | 2 | `data/experiments/B1/seed2/model.pt` | `46133eeb5e39db7c087a4b651866ce66b7ca65f2205a2c1b1b060ceb68ae3a11` |
| S5 | 0 | `data/experiments/B2/seed0/model.pt` | `8b7b38923f1f7081c885916e346f13285bee54e577945a9fae216e37ada7bdc1` |
| S5 | 1 | `data/experiments/B2/seed1/model.pt` | `6503bd457bc4823c6df0da99e7f2a5be4659bb2b1f3829e15ddc41ce54645a1b` |
| S5 | 2 | `data/experiments/B2/seed2/model.pt` | `66e0f331d9ef0af1f83c1c20103285cbb1cc28ce703cc4255020ff6daacd7c70` |

sha256 of the `final_eval.csv` files:

| file | sha256 |
|---|---|
| `data/experiments/S3/seed0/final_eval.csv` | `1fe5587e4bbe6971340dba219fb35498134c26d0f0e8544cc97b742b37bf40c8` |
| `data/experiments/S3/seed1/final_eval.csv` | `775baed31f919cedff81076f9d66272b42332472d4f0a45d83cec40e34bdb057` |
| `data/experiments/S3/seed2/final_eval.csv` | `e693d2e4a9539626d6c9a523dc281e7c3a4ce02819010dd8eb84857ff508bba6` |
| `data/experiments/S4/seed0/final_eval.csv` | `b2e98309fcdaadd3d484da1be6ed54c5f851aa02bdc5da30d9096c295f979a6e` |
| `data/experiments/S4/seed1/final_eval.csv` | `89705bf4503456a65f4371cd58b12b9a79260c1ea16e2dd5a2c503f973a42c02` |
| `data/experiments/S4/seed2/final_eval.csv` | `c4992a3fe5399a72f8419fc6821b88542b0d664b0621f0fc713a351b1a80094e` |
| `data/experiments/S5/seed0/final_eval.csv` | `81f3cd3aedde1d7aaee78e6351208ad333dd320ffe1b3518805ece4947282091` |
| `data/experiments/S5/seed1/final_eval.csv` | `356c3f98ac03741a1726802d7424afaf8f934918dceed222a33186a3fa528b8d` |
| `data/experiments/S5/seed2/final_eval.csv` | `91765cf359490f9f3002495b617fbbba895e9777820a802c1f557221863b066b` |

### Final tables

All rows of the three `final_eval.csv` files of each experiment, copied unchanged (`seed` added from the folder name). The score uses only the `greedy` rows against the three presets; the `bot:random` rows and the `sampled` rows are reported, not scored.

#### S3

| seed | step | opponent | mode | games | wins | draws | losses | win_rate | ci_low | ci_high |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 7 | 2 | 191 | 0.04 | 0.020405632066152306 | 0.07693206820093293 |
| 0 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 5 | 2 | 193 | 0.03 | 0.013820314340111346 | 0.06389429245451925 |
| 0 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 7 | 0 | 193 | 0.035 | 0.017055542008567192 | 0.07047061152229073 |
| 0 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 3 | 2 | 195 | 0.02 | 0.0078044264163494685 | 0.050287086905826436 |
| 0 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 4 | 3 | 193 | 0.0275 | 0.012253157236672575 | 0.06055567618984434 |
| 0 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 3 | 0 | 197 | 0.015 | 0.00511423779325831 | 0.04316572879269026 |
| 0 | 962560 | bot:random | greedy | 200 | 200 | 0 | 0 | 1.0 | 0.9811546736227335 | 1.0 |
| 0 | 962560 | bot:random | sampled | 200 | 199 | 0 | 1 | 0.995 | 0.9722262956021069 | 0.9991168312843989 |
| 1 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 5 | 0 | 195 | 0.025 | 0.010724719651761264 | 0.05717834040664198 |
| 1 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 6 | 4 | 190 | 0.04 | 0.020405632066152306 | 0.07693206820093293 |
| 1 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 6 | 1 | 193 | 0.0325 | 0.01542221641510996 | 0.06719816374763429 |
| 1 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 1 | 2 | 197 | 0.01 | 0.0027466581335444384 | 0.0357217617161768 |
| 1 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 6 | 2 | 192 | 0.035 | 0.017055542008567192 | 0.07047061152229073 |
| 1 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 2 | 0 | 198 | 0.01 | 0.0027466581335444384 | 0.0357217617161768 |
| 1 | 962560 | bot:random | greedy | 200 | 200 | 0 | 0 | 1.0 | 0.9811546736227335 | 1.0 |
| 1 | 962560 | bot:random | sampled | 200 | 200 | 0 | 0 | 1.0 | 0.9811546736227335 | 1.0 |
| 2 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 2 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 1 | 2 | 197 | 0.01 | 0.0027466581335444384 | 0.0357217617161768 |
| 2 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 2 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:random | greedy | 200 | 199 | 0 | 1 | 0.995 | 0.9722262956021069 | 0.9991168312843989 |
| 2 | 962560 | bot:random | sampled | 200 | 197 | 1 | 2 | 0.9875 | 0.9605077147773395 | 0.9961180920048256 |

#### S4

| seed | step | opponent | mode | games | wins | draws | losses | win_rate | ci_low | ci_high |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 2 | 1 | 197 | 0.0125 | 0.003881907995174353 | 0.03949228522266056 |
| 0 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 0 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 0 | 1 | 199 | 0.0025 | 0.0002610559935489268 | 0.023490043751831318 |
| 0 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 0 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 0 | 1 | 199 | 0.0025 | 0.0002610559935489268 | 0.023490043751831318 |
| 0 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 0 | 962560 | bot:random | greedy | 200 | 198 | 0 | 2 | 0.99 | 0.9642782382838231 | 0.9972533418664555 |
| 0 | 962560 | bot:random | sampled | 200 | 194 | 2 | 4 | 0.975 | 0.942821659593358 | 0.9892752803482386 |
| 1 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 24 | 4 | 172 | 0.13 | 0.0902820227966932 | 0.18366351872248407 |
| 1 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 10 | 2 | 188 | 0.055 | 0.03098534170345884 | 0.0957869987723084 |
| 1 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 12 | 4 | 184 | 0.07 | 0.042152171828342806 | 0.11405480885610647 |
| 1 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 3 | 1 | 196 | 0.0175 | 0.00642601313670221 | 0.04675972681736004 |
| 1 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 13 | 0 | 187 | 0.065 | 0.03837635464915299 | 0.10801907929906895 |
| 1 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 1 | 1 | 198 | 0.0075 | 0.0017339693431557834 | 0.03182867713845179 |
| 1 | 962560 | bot:random | greedy | 200 | 185 | 2 | 13 | 0.93 | 0.8859451911438936 | 0.9578478281716571 |
| 1 | 962560 | bot:random | sampled | 200 | 175 | 5 | 20 | 0.8875 | 0.836209761663897 | 0.9241851103937213 |
| 2 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:random | greedy | 200 | 198 | 2 | 0 | 0.995 | 0.9722262956021069 | 0.9991168312843989 |
| 2 | 962560 | bot:random | sampled | 200 | 199 | 0 | 1 | 0.995 | 0.9722262956021069 | 0.9991168312843989 |

#### S5

| seed | step | opponent | mode | games | wins | draws | losses | win_rate | ci_low | ci_high |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 21 | 3 | 176 | 0.1125 | 0.07581488960627872 | 0.16379023833610287 |
| 0 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 11 | 3 | 186 | 0.0625 | 0.036507488557236185 | 0.10498217202287208 |
| 0 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 15 | 2 | 183 | 0.08 | 0.049840585889759974 | 0.12598948826714396 |
| 0 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 7 | 1 | 192 | 0.0375 | 0.01871748134988186 | 0.07371444554908971 |
| 0 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 10 | 0 | 190 | 0.05 | 0.02738264560076393 | 0.08957814813877599 |
| 0 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 10 | 2 | 188 | 0.055 | 0.03098534170345884 | 0.0957869987723084 |
| 0 | 962560 | bot:random | greedy | 200 | 200 | 0 | 0 | 1.0 | 0.9811546736227335 | 1.0 |
| 0 | 962560 | bot:random | sampled | 200 | 200 | 0 | 0 | 1.0 | 0.9811546736227335 | 1.0 |
| 1 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 16 | 2 | 182 | 0.085 | 0.05374575017747561 | 0.13189587071565567 |
| 1 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 6 | 2 | 192 | 0.035 | 0.017055542008567192 | 0.07047061152229073 |
| 1 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 13 | 0 | 187 | 0.065 | 0.03837635464915299 | 0.10801907929906895 |
| 1 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 11 | 2 | 187 | 0.06 | 0.03465219425433187 | 0.1019316929576627 |
| 1 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 12 | 5 | 183 | 0.0725 | 0.044057943821951794 | 0.11705481023061112 |
| 1 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 13 | 9 | 178 | 0.0875 | 0.055712202024730345 | 0.13483519223651458 |
| 1 | 962560 | bot:random | greedy | 200 | 200 | 0 | 0 | 1.0 | 0.9811546736227335 | 1.0 |
| 1 | 962560 | bot:random | sampled | 200 | 200 | 0 | 0 | 1.0 | 0.9811546736227335 | 1.0 |
| 2 | 962560 | bot:topchip-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:topchip-draw20-pts6 | sampled | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 2 | 962560 | bot:spendmost-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:spendmost-draw20-pts6 | sampled | 200 | 1 | 1 | 198 | 0.0075 | 0.0017339693431557834 | 0.03182867713845179 |
| 2 | 962560 | bot:blackpurple-draw20-pts6 | greedy | 200 | 0 | 0 | 200 | 0.0 | 1.734723475976807e-18 | 0.018845326377266575 |
| 2 | 962560 | bot:blackpurple-draw20-pts6 | sampled | 200 | 1 | 0 | 199 | 0.005 | 0.0008831687156009814 | 0.02777370439789293 |
| 2 | 962560 | bot:random | greedy | 200 | 175 | 8 | 17 | 0.895 | 0.8448196800887696 | 0.9302925120731899 |
| 2 | 962560 | bot:random | sampled | 200 | 170 | 6 | 24 | 0.865 | 0.8107086162924745 | 0.9055342954521209 |

### Scores

Score = mean of `win_rate` over the 9 `greedy` rows against `bot:topchip-draw20-pts6`, `bot:spendmost-draw20-pts6` and `bot:blackpurple-draw20-pts6` (3 seeds x 3 presets). S2 is the reference row from part 1.

| experiment | score |
|---|---|
| S2 (reference, part 1) | 0.0181 |
| S3 | 0.0239 |
| S4 | 0.0314 |
| S5 | 0.0517 |

The snippet that computed the scores, the best BC arm and L (run from the repo root):

```python
import csv
from pathlib import Path

PRESETS = ("bot:topchip-draw20-pts6", "bot:spendmost-draw20-pts6", "bot:blackpurple-draw20-pts6")
X_SCORE = 0.018055555555555557  # S2, part 1


def score(exp: str, root: Path = Path("data/experiments")) -> float:
    """Mean greedy final win rate against the three presets over seeds 0, 1, 2 (9 rows)."""
    rates = []
    for seed in (0, 1, 2):
        with open(root / exp / f"seed{seed}" / "final_eval.csv", newline="") as f:
            for row in csv.DictReader(f):
                if row["mode"] == "greedy" and row["opponent"] in PRESETS:
                    rates.append(float(row["win_rate"]))
    assert len(rates) == 9
    return sum(rates) / len(rates)


scores = {exp: score(exp) for exp in ("S3", "S4", "S5")}
M = max(scores.values())
best = next(exp for exp in ("S3", "S5", "S4") if scores[exp] >= M - 0.01)
L = best if scores[best] - X_SCORE > 0.01 else "S2"
```

### Learning curves

Per checkpoint `step` of `eval.csv`: the mean of `win_rate` over the 9 `greedy` rows against the three presets (3 seeds x 3 presets, 50 games each). S2 is the reference column from part 1.

| step | S2 | S3 | S4 | S5 |
|---|---|---|---|---|
| 96,256 | 0.0222 | 0.1933 | 0.2933 | 0.2578 |
| 192,512 | 0.0056 | 0.0889 | 0.1967 | 0.1511 |
| 288,768 | 0.0222 | 0.0189 | 0.0900 | 0.0444 |
| 385,024 | 0.0400 | 0.0411 | 0.0422 | 0.1211 |
| 481,280 | 0.0022 | 0.0233 | 0.0189 | 0.1011 |
| 577,536 | 0.0144 | 0.0311 | 0.0200 | 0.0344 |
| 673,792 | 0.0167 | 0.0822 | 0.0111 | 0.0111 |
| 770,048 | 0.0011 | 0.0200 | 0.0256 | 0.0078 |
| 866,304 | 0.0156 | 0.0211 | 0.0133 | 0.0400 |
| 962,560 | 0.0133 | 0.0178 | 0.0189 | 0.0444 |

### Choice of the best BC arm

Rule (spec `docs/specs/2026-11-09-screening-and-bc-start.md`, "Choice rules"): M = the highest score of S3, S4, S5; the arm = the first of S3, S5, S4 whose score is >= M - 0.01 (unrounded scores, the bound counts as within).

```
M        = max(0.0239, 0.0314, 0.0517) = 0.0517
M - 0.01 = 0.0417
S3: 0.0239 < 0.0417  not within
S5: 0.0517 >= 0.0417  within
S4: 0.0314 < 0.0417  not within
```

Unrounded: S3 = 0.02388888888888889, S4 = 0.03138888888888889, S5 = 0.051666666666666666, M - 0.01 = 0.041666666666666664.

Best BC arm: S5

### Choice of the long run

Rule: the best BC arm if its score minus X's score is > 0.01 (strictly), otherwise S2 (X from scratch). X = S2 with the unrounded score 0.018055555555555557 (part 1).

```
S5 - S2 = 0.0517 - 0.0181 = 0.0336
0.0336 > 0.01
```

Unrounded: 0.051666666666666666 - 0.018055555555555557 = 0.033611111111111105.

L: S5

## Part 3: Shortcomings of stage #309

Issue: #318. Spec: `docs/specs/2026-11-11-ppo-update-size.md` ("Part 3 of the record"). This part
was written after the stage, before any new run. The numbers come from parts 1 and 2 and from the
`ppo.csv` files of the run folders.

### What went wrong

- **After S0-S2, every score was at the floor:** S0 0.0036, S1 0.0011, S2 0.0181, with 1,800
  scored greedy games each. S1 also beat `bot:random` less often than S0, although S1 trained
  against it: greedy final win rate, seeds 0, 1, 2, S1 0.955, 0.735, 0.615 against S0 0.9275,
  0.9225, 0.9775. The stage went on to screening 2 instead of asking why.
- **After S3-S5, every BC arm dropped on the learning curve** from its first checkpoint (S3
  0.1933, S4 0.2933, S5 0.2578 at step 96,256) to its last checkpoint (S3 0.0178, S4 0.0189, S5
  0.0444 at step 962,560). The final scores (S3 0.0239, S4 0.0314, S5 0.0517) stayed near the
  floor. The fixed rules still chose S5 and wrote L.
- **The stage review of #309 saw the drop** and still offered "run L = S5" as an option
  (https://github.com/Lighfe/quack-rl/issues/309#issuecomment-6776798379).
- **The training logs (`ppo.csv`) were never read.** The table below shows what they held.
- **The owner's part:** the owner did not watch the runs in the monitor.
- **What changes:** the PPO settings become config fields (#319), and every screening gets a
  sense check (`experiments/README.md`, "Sense check after a screening").

### PPO metrics

Per experiment and window: the mean over seeds 0, 1, 2 of the mean over the window's rows of
`data/experiments/<exp>/seed<k>/ppo.csv` (940 rows each, one row per update of 1,024 steps).
Windows, as 1-based data rows: first = rows 1-50, middle = rows 446-495, last = rows 891-940.

| experiment | window | `approx_kl` | `clip_fraction` | `entropy` | `explained_variance` | `mean_reward` |
|---|---|---|---|---|---|---|
| S0 | first | 0.0572 | 0.2328 | 0.4614 | 0.6754 | -0.9993 |
| S0 | middle | 0.1447 | 0.1526 | 0.1544 | 0.9557 | -0.9915 |
| S0 | last | 0.1213 | 0.1517 | 0.1707 | 0.9564 | -0.9964 |
| S1 | first | 0.0548 | 0.2458 | 0.5384 | 0.7029 | -0.7614 |
| S1 | middle | 0.1094 | 0.2166 | 0.2925 | 0.8839 | -0.7435 |
| S1 | last | 0.1133 | 0.1999 | 0.2583 | 0.8669 | -0.7674 |
| S2 | first | 0.0558 | 0.2446 | 0.5052 | 0.4201 | -0.5983 |
| S2 | middle | 0.1166 | 0.1923 | 0.2325 | 0.7332 | -0.5380 |
| S2 | last | 0.1327 | 0.1593 | 0.1764 | 0.7383 | -0.4952 |
| S3 | first | 0.0000 | 0.0000 | 0.1628 | 0.4792 | -0.0737 |
| S3 | middle | 0.1025 | 0.1700 | 0.2049 | 0.7456 | -0.5219 |
| S3 | last | 0.1252 | 0.1525 | 0.1619 | 0.7232 | -0.4852 |
| S4 | first | 0.0000 | 0.0000 | 0.4427 | 0.4928 | -0.3727 |
| S4 | middle | 0.1189 | 0.1710 | 0.2035 | 0.7179 | -0.5056 |
| S4 | last | 0.1099 | 0.1607 | 0.1832 | 0.7317 | -0.5122 |
| S5 | first | 0.0000 | 0.0000 | 0.1625 | 0.4591 | -0.0757 |
| S5 | middle | 0.1090 | 0.1712 | 0.2252 | 0.6863 | -0.4313 |
| S5 | last | 0.1039 | 0.1544 | 0.1795 | 0.7083 | -0.4721 |

The snippet that computed the table (run from the repo root):

```python
import csv
from pathlib import Path

METRICS = ("approx_kl", "clip_fraction", "entropy", "explained_variance", "mean_reward")
WINDOWS = {"first": (1, 50), "middle": (446, 495), "last": (891, 940)}  # 1-based data rows


def window_means(exp: str, root: Path = Path("data/experiments")) -> dict:
    """Per window and metric: the mean over seeds 0, 1, 2 of the mean over the window's rows."""
    out = {w: {m: 0.0 for m in METRICS} for w in WINDOWS}
    for seed in (0, 1, 2):
        with open(root / exp / f"seed{seed}" / "ppo.csv", newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 940
        for w, (lo, hi) in WINDOWS.items():
            part = rows[lo - 1 : hi]
            for m in METRICS:
                out[w][m] += sum(float(r[m]) for r in part) / len(part) / 3
    return out


for exp in ("S0", "S1", "S2", "S3", "S4", "S5"):
    for w, vals in window_means(exp).items():
        print(f"| {exp} | {w} | " + " | ".join(f"{vals[m]:.4f}" for m in METRICS) + " |")
```

### Reading of the PPO metrics

- **The updates are large.** `approx_kl` is 0.05-0.16 in every window that trains the actor
  (0.0548-0.1447 in the table), against the common 0.01-0.02.
- **The zero window of S3-S5 is the critic warmup.** In S3-S5, rows 1-50 are exactly the critic
  warmup (`critic_warmup_steps` 51,200 = 50 updates of 1,024 steps, actor frozen). So
  `approx_kl` and `clip_fraction` are 0 there; that window is not a sign of small updates.
- **The PPO setup is SB3's defaults.** `n_steps` 1,024, `batch_size` 64, `n_epochs` 10: 1,024 /
  64 x 10 = 160 gradient steps per update, on about 12 games. There is no `target_kl`, and
  `ent_coef` is 0.
- **Entropy falls even in S0**, which has almost no wins: from 0.4614 (first) to 0.1544 (middle)
  and 0.1707 (last). The policy grows sure of itself without a signal that would justify it.
- **Reading, not a test:** in S0 the critic most likely predicts how many moves are left. With
  reward `win_loss` and almost every game lost (`mean_reward` -0.9993 to -0.9915), the target is
  -0.99^k for almost every game, where k is the number of moves to the end. So
  `explained_variance` is high (0.9557, 0.9564) with no information about winning. This was not
  tested.
