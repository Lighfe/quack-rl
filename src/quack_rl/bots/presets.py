"""The three preset bots: one rule bot setting per strategy.

Picked by the baseline tournament in `docs/analysis/2026-11-bot-baseline.md` (the setting of each
strategy with the highest win rate over all its games). The web game offers them, and the RL
agents are measured against them.
"""

PRESET_BOTS: tuple[str, str, str] = (
    "bot:topchip-draw20-pts6",
    "bot:spendmost-draw20-pts6",
    "bot:blackpurple-draw20-pts6",
)

PRESET_LABELS: dict[str, str] = {
    "bot:topchip-draw20-pts6": "Top chip (draw 20 %, points from round 6)",
    "bot:spendmost-draw20-pts6": "Spend most (draw 20 %, points from round 6)",
    "bot:blackpurple-draw20-pts6": "Black, then purple (draw 20 %, points from round 6)",
}
