import asyncio
import time
import socketio
from aiohttp import web
from typing import Any, Dict
import os
from game import Game



sio = socketio.AsyncServer(async_mode="aiohttp", cors_allowed_origins="*")
app = web.Application()
sio.attach(app)



# from model import DQN


# TODO: Create a SocketIO server instance with CORS settings to allow connections from frontend
# Example: sio = socketio.AsyncServer(cors_allowed_origins="*")

# TODO: Create a web application instance
# Example: app = web.Application()

# TODO: Attach the socketio server to the web app
# Example: sio.attach(app)


# Basic health check endpoint - keep this for server monitoring
async def handle_ping(request: Any) -> Any:
    """Simple ping endpoint to keep server alive and check if it's running"""
    return web.json_response({"message": "pong"})


# TODO: Create a socketio event handler for when clients connect

@sio.event
async def connect(sid: str, environ: Dict[str, Any]) -> None:
    """
    Fired when a client opens a WebSocket.
    We create a fresh per-client session so later steps (game start, AI, etc.)
    have a place to store state.
    """
    print(f"✅ Client connected: {sid}")

    # Per-client session skeleton — we'll fill these in future steps.
    session = {
        "game": None,            # will hold a Game() instance later
        "agent": None,           # will hold the AI agent later
        "statistics": {"games": 0, "best_score": 0},
        "started": False
    }

    # Persist this session with Socket.IO so other handlers can read it
    await sio.save_session(sid, session)

    # let the client know the server is ready
    await sio.emit("server_ready", {"sid": sid}, to=sid)

    # TODO: You might want to initialize game state here
    pass


# TODO: Create a socketio event handler for when clients disconnect
@sio.event
async def disconnect(sid: str) -> None:
    """Handle client disconnections - cleanup any resources"""
    """Cleanup when a client disconnects."""
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
            if hasattr(game, "stop") and callable(game.stop):
                game.stop()
        except Exception as e:
            print(f"[disconnect] game cleanup error: {e}")
        try:
            if hasattr(agent, "close") and callable(agent.close):
                agent.close()
        except Exception as e:
            print(f"[disconnect] agent cleanup error: {e}")
    pass


# TODO: Create a socketio event handler for starting a new game
@sio.event
async def start_game(sid: str, data: Dict[str, Any]) -> None:
    """Initialize a new game when the frontend requests it"""
    # TODO: Extract game parameters from data (grid_width, grid_height, starting_tick)
    # TODO: Create a new Game instance and configure it
    # TODO: If implementing AI, create an agent instance here
    # TODO: Save the game state in the session using sio.save_session()
    # TODO: Send initial game state to the client using sio.emit()
    # TODO: Start the game update loop
    # Pull existing session (created in connect)
    session = await sio.get_session(sid)
    if session is None:
        print(f"[start_game] no session for sid={sid}")
        return

    # Get or create a Game instance
    game = session.get("game")
    if not isinstance(game, Game):
        game = Game()
    else:
        # Reset if we're restarting an existing game
        if hasattr(game, "reset") and callable(game.reset):
            game.reset()

    # Save runtime options (e.g., tick interval)
    tick_ms = int(data.get("tick_ms", session.get("tick_ms", 100)))

    # Update session and persist
    session.update({
        "game": game,
        "started": True,
        "tick_ms": tick_ms,
    })
    await sio.save_session(sid, session)

    # Tell the client we’re starting and send initial state
    try:
        initial_state = game.to_dict() if hasattr(game, "to_dict") else {}
    except Exception as e:
        print(f"[start_game] to_dict error: {e}")
        initial_state = {}

    await sio.emit("game_started", {"tick_ms": tick_ms}, to=sid)
    await sio.emit("game_state", initial_state, to=sid)

    # Launch the update loop in the background (we'll implement it next)
    import asyncio as _asyncio
    _asyncio.create_task(update_game(sid))

    pass


# TODO: Optional - Create event handlers for saving/loading AI models


# TODO: Implement the main game loop
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
    # Acquire session and set a guard so we don't run two loops per sid
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

            game: Game | None = session.get("game")
            if not isinstance(game, Game):
                break  # nothing to drive

            # Tick interval (ms) — configurable via start_game(data={"tick_ms": ...})
            tick_ms = int(session.get("tick_ms", 100))

            # Advance the game one step
            try:
                if hasattr(game, "step") and callable(game.step):
                    game.step()
            except Exception as e:
                print(f"[update_game] game.step error: {e}")
                break

            # Prepare state payload
            try:
                state = game.to_dict() if hasattr(game, "to_dict") else {}
            except Exception as e:
                print(f"[update_game] to_dict error: {e}")
                state = {}

            # Send frame to the client
            await sio.emit("game_state", state, to=sid)

            # Check terminal condition
                        # Check terminal condition WITHOUT calling game.game_over() (which ends the game)
            running = bool(getattr(game, "running", True))
            if not running:
                await sio.emit("game_over", state, to=sid)
                session["started"] = False
                await sio.save_session(sid, session)
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
    pass

VALID_DIRS = {"UP", "DOWN", "LEFT", "RIGHT"}

@sio.event
async def change_direction(sid: str, data: Dict[str, Any]) -> None:
    session = await sio.get_session(sid)
    game = session.get("game") if session else None
    if not isinstance(game, Game):
        return

    direction = str(data.get("direction", "")).upper()
    if direction not in VALID_DIRS:
        await sio.emit("error", {"type": "bad_direction", "got": data.get("direction")}, to=sid)
        return

    # ✅ Add these two lines:
    print(f"[change_direction] got {direction}, queue_len(before)={len(game.change_queue)}")
    try:
        game.queue_change(direction)
    except Exception as e:
        print(f"[change_direction] queue error: {e}")
        return
    print(f"[change_direction] queued, queue_len(after)={len(game.change_queue)}")

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




# TODO: Helper function for AI agent interaction with game
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
    pass


# TODO: Main server startup function
async def main() -> None:
    """Start the web server and socketio server"""
    # TODO: Add the ping endpoint to the web app router
    # TODO: Create and configure the web server runner
    # TODO: Start the server on the appropriate host and port
    # TODO: Print server startup message
    # TODO: Keep the server running indefinitely
    # TODO: Handle any errors gracefully
    # 1) Route for health checks
    app.router.add_get("/ping", handle_ping)

    # 2) Create and start the aiohttp server
    runner = web.AppRunner(app)
    await runner.setup()

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))

    site = web.TCPSite(runner, host=host, port=port)
    await site.start()

    print(f"🚀 Server running on http://{host}:{port}")

    # 3) Keep the server alive until interrupted
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await runner.cleanup()
    pass


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

