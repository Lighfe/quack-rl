# Brew screen polish from the first play test

Date: 2026-10-26. Source: the owner's play test of the brew screen (stage #208) and the stage review of #208.

## Intent

The owner played the first browser version and wrote down what is not as imagined. The brew screen should feel like a real game table: a dark, slightly dusty cauldron where the chips leave a trail along a visible spiral path, with pixel-art symbols instead of words. QA should check visual criteria in a real headless browser, and the app should start from the addresses the owner uses.

## Goals

1. QA runs a headless browser check itself when the QA pre-step has installed the browser.
2. The game service accepts the browser's request from the owner's other local addresses and from the Lovable preview; the start screen says why a start failed.
3. The brew screen gets the play-test changes below, one issue per group.

## Non-goals (this stage)

- Shop, spell book, point board, round card and dice visuals (#214). They come in the next stage, on top of the new look, so they are not drawn twice.
- The Voronoi pot layout. Still wanted, in a later stage; it must keep the path and the trace of this stage.
- Policy seat, replay, hosting.

## Anti-goals

- No game rule in the frontend (all numbers and positions come from the view).
- Do not overdo the mood: a palette change and a few textures, not a heavy redesign.
- No text that is not about a game component.

## QA in a headless browser

`docs/team/qa-engineer.md` says: without a browser tool, do not repeat a browser check. Under `scripts/qa-codex` the pre-step installs the Playwright browser in `frontend/`. QA should then run the browser check itself, with Playwright from `frontend/node_modules`, start server and app and script in one command, and take its own screenshot. If the browser cannot start in the sandbox, the criterion is UNVERIFIABLE as today (a change of the sandbox arguments is the owner's call, not this stage). The file is a kit copy (agent-graph-kit); the port upstream is a follow-up.

## The start from other addresses (#215)

Today the service allows only `http://localhost` and `http://127.0.0.1` origins. A preflight from a LAN IP, a Docker bridge IP or the Lovable preview gets 400, and the start screen shows only "The game could not be started."

- The default allowed origins add the private IPv4 ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), any port, http.
- `quack-rl serve --allow-origin <regex>` (repeatable) adds more origins, for example the Lovable preview origin. The README names the Lovable preview example.
- A preflight that asks for private network access (`Access-Control-Request-Private-Network: true`) gets `Access-Control-Allow-Private-Network: true` for an allowed origin (Chromium browsers need it when an https page calls the local service).
- The bind address stays `127.0.0.1` by default.
- The start screen shows the service address it tried and the reason (network or CORS error, or the HTTP status and message).

## The brew screen changes

Field numbers: field 0 is the centre. A player's droplet is at field `d` (`seats[].droplet`), the rat tails `r` (`seats[].rat_tail`). The start field is `d + r` (capped at the track end). A chip of value `v` drawn first lands on `d + r + v`.

### Look: mood, palette and pixel frames (play-test notes 5 and 7)

- The yellow field borders are too intense; the look is too clean and reads as Tetris. Aim: a bit mysterious, a bit dusty, a bit dark; the spiral is the cauldron being filled. Muted, darker borders; a worn or dusty texture; a cauldron feel for the pot (dark stone or metal, a faint glow of the brew). The whole palette (background, panels, text, accents) may change with it. The chip colours stay the game colours and stay readable.
- Pixel style is not consistent: the font is pixel art, the boxes, field borders and panel frames have smooth straight edges. They get a pixel treatment: stepped (notched) corners and borders built from visible pixel steps, optionally a light pixel texture or dither on fills.
- Keep it simple.

### Pot: spiral path and chip trail (note 3)

- Path: the fields sit on a visible spiral path. The gap between neighbouring fields along the path is small; the gap between two turns of the spiral is clearly larger, so the path and its direction can be seen (like a stone path laid in a spiral). Fields stay square.
- Trail: the fields a chip's move covers (`from` to `landing`) are drawn as one continuous trail along the path: no borders between those fields, in the chip's colour, slightly faded, and it may wobble a little (not a ruler-straight bar). The border between two chips' moves stays. The landing field (the chip with its value) stays clearly different from its trail.
- Both live on the `PotLayout` outlines, so the later Voronoi layout keeps them.

### Pot markers: droplet, rat tails, ruby (notes 1, 2, 4)

- Droplet: a big droplet icon, centred on field `d`, larger than today, its shape slightly changed from the small symmetric drop. A small droplet icon (bottom left of the field) on every field `0 .. d-1`. Droplet 0: no small drops. Droplet 1: field 0 only.
- Rat tails, same pattern: a big pixel-art rat on the start field `d + r`; a small pixel-art rat tail icon (new design, maybe a new colour) on every field `d+1 .. d+r-1`. No rat tails: no rat.
- Example `d = 3`, `r = 2`: small drops on 0 to 2, big drop on 3, small tail on 4, big rat on 5, a first chip of value 1 on 6.
- Ruby mark of a window field: same place and about the same size as today's red square, drawn as a pixel-art gem.

### Symbols instead of words (note 6)

- Seat panel: pixel symbols with the number instead of the words: money a pixel coin (classic platformer coin style), rubies the ruby gem of the pot (bigger), flask a pixel potion flask drawn full or empty, points a pixel star (owner may change the symbol at review). Droplet and Rat tail leave the panel; the pot shows them.
- Window fields: the money number (upper) and the points number (lower) each get a tiny version of the coin and the star next to them, so it is clear which is which.

### The bag as a sack (note 8)

- The bag panel becomes a brown sack (cloth or leather pouch tied at the top), like a real game component. The chips and their `xN` counts are shown inside the sack. The sack is a bit bigger than today's box and may grow with its content.

## Order

QA browser fix first (every visual issue needs it). The service fix and the start error message have no blocker between them except that the message issue shows the new behaviour. Look first among the visual issues (the others build on its palette and frames), then path and trail, then markers, then symbols (uses the ruby gem), then the sack.

## Constraints

- Lane `frontend` through Lovable (`docs/team/software-engineer.md`); `bun`; the service field names in `src/quack_rl/web/view.py`.
- Every visual issue: the engineer takes a headless Playwright screenshot and states in `## Engineer: DONE` what it shows; QA takes its own screenshot after the QA browser fix.
