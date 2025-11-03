# client_smoke.py — quick backend verifier
import asyncio, socketio

def head_xy(s):
    try: return tuple(s["snake"][0])
    except: return None

async def main():
    sio = socketio.AsyncClient()
    frames = {"n": 0}

    @sio.event
    async def connect():
        print("[client] connected")
        await sio.emit("set_seed", {"seed": 123})
        await sio.emit("start_game", {"tick_ms": 60})

    @sio.event
    async def game_started(data):
        print("[client] game_started:", data)
        await sio.emit("set_speed", {"tick_ms": 100})
        await sio.emit("set_grid", {"width": 25, "height": 15})

    @sio.event
    async def speed_set(data): print("[client] speed_set:", data)
    @sio.event
    async def grid_set(data):  print("[client] grid_set:", data)

    @sio.event
    async def game_state(state):
        frames["n"] += 1
        h = head_xy(state)
        print(f"[client] frame {frames['n']} head={h}")
        if frames["n"] == 2:
            await sio.emit("change_direction", {"direction": "RIGHT"})
            print("[client] -> change RIGHT")
        if frames["n"] == 4:
            print("[client] -> pausing")
            await sio.emit("pause_game")
        if frames["n"] == 5:
            print("[client] -> resuming")
            await sio.emit("resume_game")
        if frames["n"] == 7:
            print("[client] -> stop_game")
            await sio.emit("stop_game")

    @sio.event
    async def game_over(state=None):
        print("[client] game_over -> restarting (seed kept)")
        await sio.emit("restart_game", {"tick_ms": 80})

        @sio.event
        async def game_state(state2):
            print("[client] restarted head:", head_xy(state2))
            await sio.disconnect()

    await sio.connect("http://localhost:8000")
    await sio.wait()

if __name__ == "__main__":
    asyncio.run(main())
