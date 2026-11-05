"""The HTTP API of the local game service. Running games live in memory; each game is also saved
as a game record under `<record root>/<rules version>/web/`."""

import logging
import re
import threading
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

import typer
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from quack_rl.bots.presets import PRESET_BOTS, PRESET_LABELS
from quack_rl.record import LocalRecordStore
from quack_rl.rl.agents import AGENT_PREFIX, AGENTS_ROOT, AgentError, checked_manifest
from quack_rl.rules import Ruleset, load_ruleset, with_rounds
from quack_rl.web.session import GameSession, IllegalSubmit, StaleRevision
from quack_rl.web.view import seat_view

RULES = "v2.3"
logger = logging.getLogger(__name__)
_OCTET = r"\d{1,3}"
LOCAL_ORIGINS = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
# Private IPv4 ranges 10.0.0.0/8, 172.16.0.0/12 and 192.168.0.0/16 (LAN, Docker bridge), http only.
PRIVATE_ORIGINS = (
    rf"http://(10\.{_OCTET}|172\.(1[6-9]|2\d|3[01])|192\.168)\.{_OCTET}\.{_OCTET}(:\d+)?"
)
# This project's Lovable preview, as an exact origin (never a wildcard over *.lovable.app).
LOVABLE_ORIGINS = "|".join(
    re.escape(o) for o in ("https://id-preview--34424226-c265-4c0c-a695-30527093b97c.lovable.app",)
)
DEFAULT_ORIGINS = (LOCAL_ORIGINS, PRIVATE_ORIGINS, LOVABLE_ORIGINS)


def origin_regex(extra_origins: Sequence[str] = ()) -> str:
    """One regex for CORS: Starlette matches it against the whole origin (fullmatch)."""
    return "|".join(f"(?:{r})" for r in (*DEFAULT_ORIGINS, *extra_origins))


SeatId = Literal["p1", "p2"]


class NewGame(BaseModel):
    p1: str
    p2: str
    rounds: int = Field(default=9, ge=1)
    seed: int | None = None


class Action(BaseModel):
    seat: SeatId
    action: str
    revision: int


class Opponent(BaseModel):
    spec: str
    label: str
    kind: Literal["bot", "ppo", "bc", "cql", "planner"]


def list_opponents(rules: Ruleset, agents_root: Path) -> list[Opponent]:
    """The preset bots in `PRESET_BOTS` order, then each agent under `agents_root` that fits
    `rules`, by name. A folder that is not such an agent is left out with a WARNING record."""
    found = [Opponent(spec=s, label=PRESET_LABELS[s], kind="bot") for s in PRESET_BOTS]
    root = Path(agents_root)
    if not root.is_dir():
        return found
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            m = checked_manifest(folder.name, rules, root)
        except AgentError as err:
            logger.warning("skipped agent folder %s: %s", folder, err)
            continue
        found.append(
            Opponent(
                spec=AGENT_PREFIX + folder.name, label=f"{folder.name} ({m.kind})", kind=m.kind
            )
        )
    return found


def create_app(
    record_root: Path, extra_origins: Sequence[str] = (), agents_root: Path = AGENTS_ROOT
) -> FastAPI:
    """The game service; each game is recorded under `record_root`. `extra_origins` are origin
    regexes allowed besides the defaults. The `agent:<name>` seats come from `agents_root`."""
    app = FastAPI(title="quack-rl game service")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=origin_regex(extra_origins),
        allow_private_network=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    games: dict[str, GameSession] = {}
    app.state.games = games
    games_lock = threading.Lock()
    base = load_ruleset(RULES)
    store = LocalRecordStore(Path(record_root))

    def session_of(game_id: str) -> GameSession:
        session = games.get(game_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"unknown game {game_id!r}")
        return session

    @app.post("/games")
    def create_game(body: NewGame) -> dict[str, str]:
        game_id = uuid.uuid4().hex
        try:
            session = GameSession.create(
                with_rounds(base, body.rounds),
                {"p1": body.p1, "p2": body.p2},
                body.seed,
                store=store,
                game_id=game_id,
                agents_root=agents_root,
            )
        except typer.BadParameter as e:
            raise HTTPException(status_code=400, detail=e.message) from None
        with games_lock:
            games[game_id] = session
        return {"game_id": game_id}

    @app.get("/opponents")
    def get_opponents() -> list[Opponent]:
        return list_opponents(base, agents_root)

    @app.get("/games/{game_id}/view")
    def get_view(game_id: str, seat: SeatId) -> dict[str, Any]:
        session = session_of(game_id)
        with session.lock:
            return seat_view(session, seat)

    @app.post("/games/{game_id}/actions")
    def post_action(game_id: str, body: Action) -> Any:
        session = session_of(game_id)
        with session.lock:
            try:
                session.submit(body.seat, body.action, body.revision)
            except IllegalSubmit as e:
                return JSONResponse(
                    status_code=400, content={"error": "illegal_action", "legal": e.legal}
                )
            except StaleRevision:
                return JSONResponse(
                    status_code=409,
                    content={"error": "stale_revision", "revision": session.revision},
                )
            return seat_view(session, body.seat)

    return app
