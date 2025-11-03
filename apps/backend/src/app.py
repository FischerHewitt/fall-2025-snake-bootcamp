# app.py — Snake Bootcamp backend (aiohttp + python-socketio)
# This version preserves the scaffold's TODO comments and implements code directly underneath them.

import os
import random
import asyncio
from typing import Any, Dict, Optional

import socketio
from aiohttp import web

from game import Game
# from model import DQN  # (Optional) AI agent — not used yet


# TODO: Create a SocketIO server instance with CORS settings to allow connections from frontend
# Example: sio = socketio.AsyncServer(cors_allowed_origins="*")
# --- IMPLEMENTATION ---
sio = socketio.AsyncServer(async_mode="aiohttp", cors_allowed_origins="*")

# TODO: Create a web application instance
# Example: app = web.Application()
# --- IMPLEMENTATION ---
app = web.Application()

# TODO: Attach the socketio server to the web app
# Example: sio.attach(app)
# --- IMPLEMENTATION ---
sio.attach(app)


# Basic health check endpoint - keep this for server monitoring
async def handle_ping(request: Any) -> Any:
    """Simple ping endpoint to keep server alive and check if it's running"""
    return web.json_response({"message": "pong"})


# TODO: Create a socketio event handler for when clients connect
# --- IMPLEMENTATION ---
@sio.event
async def connect(sid: str, environ: Dict[str, Any]) -> None:
    """Handle client connections - called when a frontend connects to the server"""
    # TODO: Print a message showing which client connected
    # --- IMPLEMENTATION ---
    print(f"✅ Client connected: {sid}")

    # Initialize per-connection session state
    session: Dict[str, Any] = {
        "game": None,            # will hold a Game instance after start_game
        "agent": None,           # (optional) your AI agent object
        "statistics": {"games": 0, "best_score": 0, "last_score": 0},
        "created_at": asyncio.get_event_loop().time(),
        "last_seen": asyncio.get_event_loop().time(),
        "started": False,
        "paused": False,
        "tick_ms": 100,
        "seed": None,
        "primed": False,         # ensure we emit an initial frame before movement
        "loop_running": False,   # guard to avoid two loops per sid
    }

    # Persist this session with Socket.IO so other handlers can use it
    await sio.save_session(sid, session)

    # Let just this client know the server is ready
    await sio.emit("server_ready", {"sid": sid, "message": "server_ready"}, room=sid)


# TODO: Create a socketio event handler for when clients disconnect
# --- IMPLEMENTATION ---
@sio.event
async def disconnect(sid: str) -> None:
    """Handle client disconnections - cleanup any resources"""
    print(f"[disconnect] client disconnected: {sid}")
    try:
        session = await sio.get_session(sid)
    except Exception:
        session = None

    if session:
        game = session.get("game")
        agent = session.get("agent")
        # Best-effort cleanup—only if these objects exist and expose cleanup hooks
        try:
            if hasattr(game, "stop") and callable(getattr(game, "stop")):
                game.stop()
        except Exception as e:
            print(f"[disconnect] game cleanup error: {e}")
        try:
            if hasattr(agent, "close") and callable(getattr(agent, "close")):
                agent.close()
        except Exception as e:
            print(f"[disconnect] agent cleanup error: {e}")


# TODO: Create a socketio event handler for starting a new game
# --- IMPLEMENTATION ---
@sio.event
async def start_game(sid: str, data: Dict[str, Any]) -> None:
    """Initialize a new game when the frontend requests it"""
    # TODO: Extract game parameters from data (grid_width, grid_height, starting_tick)
    # --- IMPLEMENTATION ---
    session = await sio.get_session(sid)
    if session is None:
        print(f"[start_game] no session for sid={sid}")
        return

    tick_ms = int(data.get("tick_ms", session.get("tick_ms", 100)))

    # Optional deterministic start via seed (respects previously set seed too)
    seed = data.get("seed", session.get("seed"))
    if seed is not None:
        try:
            random.seed(int(seed))
        except Exception as e:
            print(f"[start_game] bad seed: {e}")

    # If width/height provided on start, carry them into the new game
    gw = data.get("grid_width") or data.get("width")
    gh = data.get("grid_height") or data.get("height")

    # TODO: Create a new Game instance and configure it
    # --- IMPLEMENTATION ---
    game = Game()
    if gw and gh:
        try:
            w, h = int(gw), int(gh)
            if w >= 5 and h >= 5:
                game.grid_width = w
                game.grid_height = h
                if hasattr(game, "reset") and callable(game.reset):
                    game.reset()
        except Exception as e:
            print(f"[start_game] grid params invalid: {e}")

    # TODO: If implementing AI, create an agent instance here
    # --- IMPLEMENTATION ---
    agent = None  # Not used in the base bootcamp backend

    # TODO: Save the game state in the session using sio.save_session()
    # --- IMPLEMENTATION ---
    session.update({
        "game": game,
        "agent": agent,
        "started": True,
        "paused": False,
        "tick_ms": tick_ms,
        "primed": False,   # prime first frame before any movement
    })
    await sio.save_session(sid, session)

    # TODO: Send initial game state to the client using sio.emit()
    # --- IMPLEMENTATION ---
    try:
        initial_state = game.to_dict()
    except Exception as e:
        print(f"[start_game] to_dict error: {e}")
        initial_state = {}
    await sio.emit("game_started", {"tick_ms": tick_ms}, to=sid)
    await sio.emit("game_state", initial_state, to=sid)

    # TODO: Start the game update loop
    # --- IMPLEMENTATION ---
    asyncio.create_task(update_game(sid))


# TODO: Optional - Create event handlers for saving/loading AI models
# --- IMPLEMENTATION (stubs; frontend can handle "not_implemented") ---
@sio.event
async def save_model(sid: str, data: Dict[str, Any]) -> None:
    await sio.emit("error", {"type": "not_implemented", "op": "save_model"}, to=sid)

@sio.event
async def load_model(sid: str, data: Dict[str, Any]) -> None:
    await sio.emit("error", {"type": "not_implemented", "op": "load_model"}, to=sid)


# Convenience utilities the guide allows/recommends:

@sio.event
async def get_state(sid: str) -> None:
    """Send the current game state to just this client."""
    session = await sio.get_session(sid)
    game = session.get("game") if session else None
    state: Dict[str, Any] = {}
    if isinstance(game, Game) and hasattr(game, "to_dict"):
        try:
            state = game.to_dict()
        except Exception as e:
            print(f"[get_state] to_dict error: {e}")
    await sio.emit("game_state", state, to=sid)


@sio.event
async def set_grid(sid: str, data: Dict[str, Any]) -> None:
    """
    Update grid size and reset the game.
    Frontend sends: {"width": int, "height": int}
    """
    session = await sio.get_session(sid)
    if not session:
        return

    game = session.get("game")
    if not isinstance(game, Game):
        game = Game()

    try:
        w = int(data.get("width"))
        h = int(data.get("height"))
        if w < 5 or h < 5:
            raise ValueError("grid too small")
    except Exception:
        await sio.emit("error", {"type": "bad_grid", "got": data}, to=sid)
        return

    # apply + reset
    game.grid_width = w
    game.grid_height = h
    if hasattr(game, "reset") and callable(game.reset):
        game.reset()

    session["game"] = game
    session["primed"] = False
    await sio.save_session(sid, session)

    # confirm + send fresh state
    await sio.emit("grid_set", {"grid_width": w, "grid_height": h}, to=sid)
    try:
        state = game.to_dict()
    except Exception:
        state = {}
    await sio.emit("game_state", state, to=sid)


@sio.event
async def set_speed(sid: str, data: Dict[str, Any]) -> None:
    """
    Update tick interval (ms) for this client's game loop.
    Frontend sends: {"tick_ms": int}
    """
    session = await sio.get_session(sid)
    if not session:
        return
    try:
        tick_ms = int(data.get("tick_ms"))
    except Exception:
        await sio.emit("error", {"type": "bad_tick_ms", "got": data.get("tick_ms")}, to=sid)
        return

    session["tick_ms"] = max(1, tick_ms)
    await sio.save_session(sid, session)
    await sio.emit("speed_set", {"tick_ms": session["tick_ms"]}, to=sid)


@sio.event
async def set_seed(sid: str, data: Dict[str, Any]) -> None:
    """
    Save a RNG seed for deterministic starts.
    Frontend sends: {"seed": int}
    """
    session = await sio.get_session(sid)
    if not session:
        return
    try:
        seed = int(data.get("seed"))
    except Exception:
        await sio.emit("error", {"type": "bad_seed", "got": data.get("seed")}, to=sid)
        return
    session["seed"] = seed
    await sio.save_session(sid, session)
    await sio.emit("seed_set", {"seed": seed}, to=sid)


# Player input
VALID_DIRS = {"UP", "DOWN", "LEFT", "RIGHT"}

@sio.event
async def change_direction(sid: str, data: Dict[str, Any]) -> None:
    """
    Frontend sends: {"direction": "UP"|"DOWN"|"LEFT"|"RIGHT"}
    We queue the change so it's applied on the next tick.
    """
    session = await sio.get_session(sid)
    game = session.get("game") if session else None
    if not isinstance(game, Game):
        return

    direction = str(data.get("direction", "")).upper()
    if direction not in VALID_DIRS:
        await sio.emit("error", {"type": "bad_direction", "got": data.get("direction")}, to=sid)
        return

    try:
        game.queue_change(direction)
    except Exception as e:
        print(f"[change_direction] queue error: {e}")


@sio.event
async def pause_game(sid: str) -> None:
    """Pause this client's game (the loop will keep emitting state without moving)."""
    session = await sio.get_session(sid)
    if not session:
        return
    session["paused"] = True
    await sio.save_session(sid, session)
    await sio.emit("paused", {"paused": True}, to=sid)


@sio.event
async def resume_game(sid: str) -> None:
    """Resume this client's game."""
    session = await sio.get_session(sid)
    if not session:
        return
    session["paused"] = False
    await sio.save_session(sid, session)
    await sio.emit("paused", {"paused": False}, to=sid)


@sio.event
async def stop_game(sid: str) -> None:
    """Stop the current game loop for this client."""
    session = await sio.get_session(sid)
    if not session:
        return
    game = session.get("game")
    if isinstance(game, Game):
        game.running = False  # update_game() will detect this and emit "game_over"
    session["started"] = False
    await sio.save_session(sid, session)


@sio.event
async def restart_game(sid: str, data: Optional[Dict[str, Any]] = None) -> None:
    """
    Restart the user's game with deterministic semantics identical to start_game.
    Optional: data={"tick_ms": int, "seed": int}
    """
    data = data or {}
    session = await sio.get_session(sid)
    if session is None:
        return

    # Optional deterministic restart
    seed = data.get("seed", session.get("seed"))
    if seed is not None:
        try:
            random.seed(int(seed))
        except Exception as e:
            print(f"[restart_game] bad seed: {e}")

    # Fresh game so RNG call order matches start_game
    game = Game()

    # Tick override (if provided)
    tick_ms = int(data.get("tick_ms", session.get("tick_ms", 100)))

    # Save session
    session.update({
        "game": game,
        "started": True,
        "tick_ms": tick_ms,
        "paused": False,
        "primed": False,
    })
    await sio.save_session(sid, session)

    # Send initial state + start loop
    try:
        initial_state = game.to_dict()
    except Exception as e:
        print(f"[restart_game] to_dict error: {e}")
        initial_state = {}

    await sio.emit("game_started", {"tick_ms": tick_ms}, to=sid)
    await sio.emit("game_state", initial_state, to=sid)

    asyncio.create_task(update_game(sid))


@sio.event
async def get_stats(sid: str) -> None:
    """Return per-user gameplay stats (games played, best_score, last_score)."""
    session = await sio.get_session(sid)
    stats = (session.get("statistics") if session else None) or {}
    # defaults
    stats.setdefault("games", 0)
    stats.setdefault("best_score", 0)
    stats.setdefault("last_score", 0)
    await sio.emit("stats", stats, to=sid)


# TODO: Implement the main game loop
# --- IMPLEMENTATION ---
async def update_game(sid: str) -> None:
    """Main game loop - runs continuously while the game is active"""
    # TODO: Create an infinite loop
    # TODO: Check if the session still exists (client hasn't disconnected)
    # TODO: Get the current game and agent state from the session
    # TODO: Implement AI agentic decisions
    # TODO: Update the game state (move snake, check collisions, etc.)
    # TODO: Save the updated session
    # TODO: Send the updated game state to the client
    # TODO: Wait for the appropriate game tick interval before next update
    # --- IMPLEMENTATION ---
    try:
        session = await sio.get_session(sid)
    except Exception:
        return

    if session.get("loop_running"):
        return

    session["loop_running"] = True
    await sio.save_session(sid, session)

    try:
        while True:
            # Refresh session each tick (client might disconnect or change settings)
            try:
                session = await sio.get_session(sid)
            except Exception:
                break  # session vanished (likely disconnected)

            game: Optional[Game] = session.get("game")
            if not isinstance(game, Game):
                break  # nothing to drive

            # Tick interval (ms) — configurable via start_game(data={"tick_ms": ...})
            tick_ms = int(session.get("tick_ms", 100))

            # Handle paused state: emit state, but don't advance the game
            if session.get("paused"):
                try:
                    state = game.to_dict()
                except Exception:
                    state = {}
                await sio.emit("game_state", state, to=sid)
                await asyncio.sleep(max(tick_ms, 1) / 1000.0)
                continue

            # First-tick prime: guarantee clients see an unmoved state before any step
            if not session.get("primed"):
                session["primed"] = True
                await sio.save_session(sid, session)
                try:
                    state = game.to_dict()
                except Exception:
                    state = {}
                await sio.emit("game_state", state, to=sid)
                await asyncio.sleep(max(tick_ms, 1) / 1000.0)
                continue

            # Advance the game one step
            try:
                game.step()
            except Exception as e:
                print(f"[update_game] game.step error: {e}")
                break

            # Prepare state payload
            try:
                state = game.to_dict()
            except Exception as e:
                print(f"[update_game] to_dict error: {e}")
                state = {}

            # Send frame to the client
            await sio.emit("game_state", state, to=sid)

            # Check terminal condition WITHOUT calling game.game_over() (which ends the game)
            running = bool(getattr(game, "running", True))
            if not running:
                # --- update per-user stats ---
                try:
                    stats = session.get("statistics") or {}
                    score = int(getattr(game, "score", 0))
                    stats["games"] = int(stats.get("games", 0)) + 1
                    stats["best_score"] = max(int(stats.get("best_score", 0)), score)
                    stats["last_score"] = score
                    session["statistics"] = stats
                except Exception as e:
                    print(f"[update_game] stats update error: {e}")

                session["started"] = False
                await sio.save_session(sid, session)

                # Notify client with the final state (already includes "score")
                await sio.emit("game_over", state, to=sid)
                break

            # Sleep until next tick
            await asyncio.sleep(max(tick_ms, 1) / 1000.0)
    finally:
        # Clear the loop-running guard
        try:
            session = await sio.get_session(sid)
            session["loop_running"] = False
            await sio.save_session(sid, session)
        except Exception:
            pass


# TODO: Helper function for AI agent interaction with game
# --- IMPLEMENTATION (stub for future agent work) ---
async def update_agent_game_state(game: Game, agent: Any) -> None:
    """Handle AI agent decision making and training"""
    # TODO: Get the current game state for the agent
    # TODO: Have the agent choose an action (forward, turn left, turn right)
    # TODO: Convert the agent's action to a game direction
    # TODO: Apply the direction change to the game
    # TODO: Step the game forward one frame
    # TODO: Calculate the reward for this action
    # TODO: Get the new game state after the action
    # TODO: Train the agent on this experience (short-term memory)
    # TODO: Store this experience in the agent's memory
    # TODO: If the game ended:
    #   - Train the agent's long-term memory
    #   - Update statistics (games played, average score)
    #   - Reset the game for the next round
    # --- IMPLEMENTATION ---
    return  # intentionally not implemented in the base backend


# TODO: Main server startup function
# --- IMPLEMENTATION ---
async def main() -> None:
    """Start the web server and socketio server"""
    # TODO: Add the ping endpoint to the web app router
    # --- IMPLEMENTATION ---
    app.router.add_get("/ping", handle_ping)

    # TODO: Create and configure the web server runner
    # TODO: Start the server on the appropriate host and port
    # TODO: Print server startup message
    # TODO: Keep the server running indefinitely
    # TODO: Handle any errors gracefully
    # --- IMPLEMENTATION ---
    runner = web.AppRunner(app)
    await runner.setup()

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))

    site = web.TCPSite(runner, host=host, port=port)
    await site.start()

    print(f"🚀 Server running on http://{host}:{port}")

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

