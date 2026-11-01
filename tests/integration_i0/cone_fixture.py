"""Test-only controls around the standalone loopback synthetic demo."""

from fastapi import Request, HTTPException
from robot_dashboard.api.dependencies import require_same_origin
from experiments.expansion_20261101.cone_display.demo import compose_demo

state = compose_demo()
original = dict(state.context)


@state.app.post("/__i0_test__/cone")
async def control(request: Request):
    state.owner.authorize(request)
    require_same_origin(request)
    if request.headers.get("x-i0-synthetic-fixture") != "local-test-only":
        raise HTTPException(403)
    command = (await request.json()).get("command")
    if command == "reset":
        generation = state.scene.map_binding["generation"] + 1
        state.context.clear()
        state.context.update(original, generation=generation)
        state.scene.reset(
            {k: state.context[k] for k in ("map_id", "revision", "generation")},
            state.context["stream_epoch"],
        )
        state.owner.scene = state.scene
        state.running = True
        state.empty = False
        state.offer()
    elif command == "stop":
        state.running = False
    elif command == "empty":
        state.empty = True
        state.offer()
    elif command == "unavailable":
        state.owner.scene = None
    elif command == "mismatch":
        state.context["generation"] += 1
    else:
        raise HTTPException(400)
    return {"synthetic_only": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(state.app, host="127.0.0.1", port=4192, log_level="warning")
