"""Count wins, draws and losses per pairing of a tournament `results.csv`.

Usage: python tournament-summary.py <results.csv> <summary.csv> [short-name-of-the-policy-run]
Columns as in docs/analysis/2026-10-selfplay-first-run/tournament-summary.csv. Pairings keep the
order of the file. The policy seat `policy:<path>` is written as the short name (default: the
last part of the path).
"""
import csv
import sys
from collections import OrderedDict

src, out = sys.argv[1], sys.argv[2]
short = lambda n: (sys.argv[3] if len(sys.argv) > 3 else n.rsplit("/", 1)[-1]) if n.startswith("policy:") else n  # noqa: E731
rows: OrderedDict = OrderedDict()
with open(src, newline="") as f:
    for r in csv.DictReader(f):
        key = (short(r["p1"]), short(r["p2"]))
        c = rows.setdefault(key, [0, 0, 0, 0])
        c[0] += 1
        c[{"p1": 1, "draw": 2, "p2": 3}[r["winner"]]] += 1
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["p1", "p2", "games", "p1_wins", "draws", "p1_losses", "p1_win_rate"])
    for (a, b), (g, wi, d, lo) in rows.items():
        w.writerow([a, b, g, wi, d, lo, f"{wi / g:.3f}"])
