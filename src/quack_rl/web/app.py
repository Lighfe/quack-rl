"""The HTTP API of the local game service. Games live in memory."""

import threading
import uuid
from collections.abc import Sequence
from typing import Any, Literal

import typer
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from quack_rl.rules import load_ruleset, with_rounds
from quack_rl.web.session import GameSession, IllegalSubmit, StaleRevision
from quack_rl.web.view import seat_view

RULES = "v2.1"
_OCTET = r"\d{1,3}"
LOCAL_ORIGINS = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
# Private IPv4 ranges 10.0.0.0/8, 172.16.0.0/12 and 192.168.0.0/16 (LAN, Docker bridge), http only.
PRIVATE_ORIGINS = (
    rf"http://(10\.{_OCTET}|172\.(1[6-9]|2\d|3[01])|192\.168)\.{_OCTET}\.{_OCTET}(:\d+)?"
)
DEFAULT_ORIGINS = (LOCAL_ORIGINS, PRIVATE_ORIGINS)


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


def create_app(extra_origins: Sequence[str] = ()) -> FastAPI:
    """The game service; `extra_origins` are origin regexes allowed besides the defaults."""
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

    def session_of(game_id: str) -> GameSession:
        session = games.get(game_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"unknown game {game_id!r}")
        return session

    @app.post("/games")
    def create_game(body: NewGame) -> dict[str, str]:
        try:
            session = GameSession.create(
                with_rounds(base, body.rounds), {"p1": body.p1, "p2": body.p2}, body.seed
            )
        except typer.BadParameter as e:
            raise HTTPException(status_code=400, detail=e.message) from None
        game_id = uuid.uuid4().hex
        with games_lock:
            games[game_id] = session
        return {"game_id": game_id}

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
