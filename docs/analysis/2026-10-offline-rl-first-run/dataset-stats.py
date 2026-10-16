"""Per recorded bot: share of games and win rate of the recording seat.

Reads only the columns episode, reward, bot of the Parquet file (not obs).
Usage: uv run python docs/analysis/2026-10-offline-rl-first-run/dataset-stats.py \
    data/datasets/full.parquet docs/analysis/2026-10-offline-rl-first-run/dataset-stats.csv
A win is an episode whose rewards sum to more than 0, a loss below 0, a draw exactly 0.
"""
import csv
import sys
from collections import defaultdict

import pyarrow.parquet as pq

src, out = sys.argv[1], sys.argv[2]
t = pq.read_table(src, columns=["episode", "reward", "bot"])
total = defaultdict(float)
bot_of = {}
for ep, r, b in zip(
    t["episode"].to_pylist(), t["reward"].to_pylist(), t["bot"].to_pylist(), strict=True
):
    total[ep] += r
    bot_of[ep] = b
n = len(total)
stats = defaultdict(lambda: [0, 0, 0, 0])  # games, wins, draws, losses
for ep, s in total.items():
    row = stats[bot_of[ep]]
    row[0] += 1
    row[1 if s > 1e-6 else 3 if s < -1e-6 else 2] += 1
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["bot", "games", "share", "wins", "draws", "losses", "win_rate"])
    for b, (g, wi, d, lo) in sorted(stats.items()):
        w.writerow([b, g, f"{g / n:.4f}", wi, d, lo, f"{wi / g:.4f}"])
    w.writerow(["all", n, "1.0000", *[sum(s[i] for s in stats.values()) for i in (1, 2, 3)],
                f"{sum(s[1] for s in stats.values()) / n:.4f}"])
