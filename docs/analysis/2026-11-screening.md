# Screening (November 2026)

Stage: #309. Spec: `docs/specs/2026-11-09-screening-and-bc-start.md` ("Choice rules", "The
screening record"). Part 1 is the screening of S0, S1 and S2 and the choice of X. Part 2 (S3-S5
and the long run) is #314. The full report is #298.

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
