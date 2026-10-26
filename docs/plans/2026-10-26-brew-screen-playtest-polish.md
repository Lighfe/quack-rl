# Brew screen polish from the first play test: implementation plan

Each task becomes one GitHub issue (`docs/task-template.md`) of one stage, run by the loop in `docs/process.md`. Steps use checkbox (`- [ ]`) syntax.

**Goal:** QA checks visuals in a headless browser, the app starts from the owner's other addresses and the Lovable preview, and the brew screen gets the play-test changes (look, spiral path and trail, markers, symbols, sack).

**Architecture:** the service change is in `quack_rl.web.app` and the `serve` command. All frontend changes go through Lovable in the submodule `frontend/` and only render the view; the pot drawing stays on the `PotLayout` outlines.

**Tech stack:** Python 3.12, FastAPI, typer, pytest; React + TypeScript + Tailwind (Lovable), Playwright for screenshots.

**Spec:** `docs/specs/2026-10-26-brew-screen-playtest-polish.md`.

## Global constraints

- Frontend: lane `frontend` (`docs/team/software-engineer.md`), changes only through Lovable, `bun`, no game rule in the app, no text that is not about a game component, `cd frontend && bun install --frozen-lockfile && bun run build` exits 0, the submodule is pinned to a commit whose message contains `X-Lovable-Edit-ID:`.
- Every visual task: the engineer takes a headless Playwright screenshot (Playwright from `frontend/node_modules`) of the screen in a mock or service view that shows the case, and `## Engineer: DONE` states in words what it shows; QA takes its own screenshot (task 1).
- Field numbers: droplet `d` = `seats[].droplet`, rat tails `r` = `seats[].rat_tail`; start field `d + r`.
- Keep the mood simple: palette and a few textures, no heavy redesign. Chip colours stay the game colours.
- Test command: `uv run --with pytest pytest`.

## Review focus

1. Droplet 0 and no rat tails: no small drops, no rat; the big drop on field 0 (task 6).
2. One rat tail: big rat on `d + 1`, no small tail (task 6).
3. A chip of value 1 right after the start field: its trail is only its landing field, no empty trail drawn (task 5).
4. Two chips of the same colour next to each other: the border between their moves stays (task 5).
5. A preflight from a public origin that is not allowed (`https://example.com`): still rejected (task 2).

---

### Task 1: QA runs the browser check in a headless browser

**Files:** Modify `docs/team/qa-engineer.md` (the paragraph "If your tool list has a browser tool …").

- [ ] **Step 1:** Rewrite the paragraph: when the pre-step of `scripts/qa-codex` has installed the Playwright browser in `frontend/` (or the tool list has a browser tool), QA runs the browser check itself: start the service and `bun run dev` (or `bun run preview` after the build), run a Playwright script from `frontend/node_modules` against it, and stop them, all in one command; it saves its own screenshot under `/tmp` and describes it. QA writes the script outside the repo. When the browser does not start in the sandbox, the criterion is UNVERIFIABLE with the error quoted.
- [ ] **Step 2:** `git diff` shows only that paragraph; the full test command passes. Commit.

### Task 2: The service accepts the owner's other addresses and extra origins (#215, service part)

**Files:** Modify `src/quack_rl/web/app.py` (`LOCAL_ORIGINS`, `create_app`), `src/quack_rl/cli/main.py` (`serve`), `README.md` (Web service). Test: `tests/test_web_app.py` (or the existing web test file).

**Interfaces:** Produces `create_app(extra_origins: Sequence[str] = ()) -> FastAPI`; `quack-rl serve --allow-origin <regex>` (repeatable).

- [ ] **Step 1: Write the failing tests:** preflight `OPTIONS /games` with `Access-Control-Request-Method: POST` returns 200 and echoes the origin for `http://192.168.1.20:8080`, `http://10.0.0.5:8080`, `http://172.17.0.1:8080`; still 400 for `https://example.com` and `http://172.32.0.1:8080`; `create_app(extra_origins=[r"https://[a-z0-9-]+\.lovable\.app"])` allows `https://foo.lovable.app`; a preflight from an allowed origin with `Access-Control-Request-Private-Network: true` gets `Access-Control-Allow-Private-Network: true`, from a rejected origin it does not.
- [ ] **Step 2:** Run them: FAIL.
- [ ] **Step 3:** Extend the regex with the private IPv4 ranges; join the extra origins into the regex; add the private-network header for allowed origins; add the `serve` option. Bind stays `127.0.0.1`.
- [ ] **Step 4:** Tests pass; README names `--allow-origin` with a Lovable preview example. Full test command passes. Commit.

### Task 3 (Lane: frontend): The start screen says why a start failed (#215, app part)

- [ ] The start screen error shows the service base URL it called and the reason: the HTTP status and the service message, or "service not reachable" for a network or CORS error. The headless check: service stopped, press Start, the message names the URL.

### Task 4 (Lane: frontend): Look: dusty dark palette and pixel frames

- [ ] Field borders muted and darker (no saturated yellow); pot drawn as dark stone or metal with a faint glow; palette of background, panels, text and accents adjusted; a light dusty texture; chip colours unchanged.
- [ ] Panel frames, field borders and buttons get stepped (notched) pixel corners and pixel-step borders, no smooth rounded corners.

### Task 5 (Lane: frontend): Pot: spiral path and chip trail

- [ ] `PotLayout` keeps one module; the gap between turns of the spiral is clearly larger than between neighbours along the path.
- [ ] Each chip's covered fields `from .. landing` are one continuous trail without inner borders, in the chip colour, slightly faded, slightly wobbly; borders between chips' moves stay; the landing field stays distinct.

### Task 6 (Lane: frontend): Pot markers: droplet, rat tails, ruby

- [ ] Big drop on field `d` (centred, bigger), small drops on `0 .. d-1`; big pixel rat on `d + r`, small pixel tails on `d+1 .. d+r-1`; ruby mark a pixel gem at today's place and size.

### Task 7 (Lane: frontend): Symbols instead of words

- [ ] Seat panel: coin (money), gem (rubies), flask full or empty, star (points), with numbers; no Droplet and Rat tail rows. Window fields: tiny coin next to the money number, tiny star next to the points number.

### Task 8 (Lane: frontend): The bag as a sack

- [ ] Brown pixel sack tied at the top, bigger than today's box, chips with `xN` inside it; it may grow with the chip count.

---

## Order and blockers

1 has no blocker. 2 has no blocker. 3 needs 1 and 2. 4 needs 1. 5 needs 4. 6 needs 5. 7 needs 6. 8 needs 7 (one Lovable app, one change at a time).
