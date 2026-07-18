"""The watchable dashboard (FR-OB-03) — swarm view + per-agent inspector.

Two modes over one small FastAPI app:

* **Live** — during a run, the engine publishes each agent's lifecycle to a
  :class:`~stampede.observer.live.LiveHub`; the ``/ws`` endpoint replays the current
  snapshot to a joining browser, then streams new events as the swarm moves. This is
  the "watch the swarm hit your system" demo (driven by ``run.serve_live``).
* **Post-run** — ``serve(store)`` reconstructs the final agent states from the trace
  store and serves them once (no hub).

Requires the ``[dashboard]`` extra.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from stampede.trace.schema import GenAI, Swarmproof
from stampede.trace.store import TraceStore

# fastapi is optional (the [dashboard] extra). Import at module level — not inside
# build_app — so FastAPI can resolve the stringized `sock: WebSocket` annotation
# (PEP 563) against module globals; a local import leaves it unresolvable.
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - env-dependent
    _HAS_FASTAPI = False

if TYPE_CHECKING:
    from stampede.observer.live import LiveHub

_PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>stampede — swarm</title>
<style>
 body{margin:0;background:#1b1712;color:#faf6f0;font:14px system-ui}
 header{padding:14px 20px;border-bottom:3px solid #6b1f2a;display:flex;gap:16px;align-items:baseline}
 h1{margin:0;font-size:18px} small{color:#b89}
 #counts{margin-left:auto;color:#b89;font-size:12px}
 #swarm{display:flex;flex-wrap:wrap;gap:6px;padding:20px;max-width:1100px}
 .dot{width:16px;height:16px;border-radius:50%;background:#8f2d3b;cursor:pointer;
   opacity:.9;transition:background .2s}
 .dot.PLANNING{background:#8a6d3b} .dot.ACTING{background:#3b6ea5}
 .dot.WAITING{background:#5a5a8f} .dot.RECOVERING{background:#b8860b}
 .dot.DONE{background:#2f7d4f} .dot.FAILED{background:#b03030}
 .dot.misuse{box-shadow:0 0 0 2px #e0b040}
 #inspector{position:fixed;right:0;top:0;width:340px;height:100%;background:#241d17;
   border-left:1px solid #3a2f26;padding:20px;overflow:auto;font-size:13px}
 .k{color:#b89;text-transform:uppercase;font-size:10px;letter-spacing:.08em;margin-top:12px}
 code{color:#e9b}
</style></head><body>
<header><h1>stampede · the swarm <small id=meta></small></h1><div id=counts></div></header>
<div id=swarm></div>
<div id=inspector><div class=k>inspector</div><div id=idet>click an agent…</div></div>
<script>
let agents={};
const TERMINAL={DONE:1,FAILED:1};
function draw(){const s=document.getElementById('swarm');s.innerHTML='';
 const c={};
 for(const id of Object.keys(agents).sort()){const a=agents[id];
  c[a.state]=(c[a.state]||0)+1;
  const d=document.createElement('div');d.className='dot '+(a.state||'')+(a.misuse?' misuse':'');
  d.title=id+' · '+a.state;d.onclick=()=>show(id);s.appendChild(d);}
 document.getElementById('counts').textContent=
  Object.entries(c).map(([k,v])=>k+' '+v).join('  ·  ');}
function show(id){const a=agents[id];document.getElementById('idet').innerHTML=
 `<b>${id}</b><div class=k>persona</div>${a.persona}<div class=k>state</div>${a.state}`+
 `<div class=k>goal</div>${a.goal||''}<div class=k>called</div><code>${a.tool||'—'}</code>`+
 `<div class=k>why did you call X?</div>${a.reasoning||'—'}`+
 `<div class=k>misuse</div>${a.misuse}`;}
const ws=new WebSocket(`ws://${location.host}/ws`);
ws.onmessage=e=>{const m=JSON.parse(e.data);
 if(m.meta){document.getElementById('meta').textContent='· '+m.meta;return;}
 agents[m.id]=Object.assign(agents[m.id]||{},m);draw();};
</script></body></html>"""


def _agents_from_store(store: TraceStore) -> dict[str, dict[str, Any]]:
    """Reconstruct final agent states from the trace store (post-run mode)."""
    agents: dict[str, dict[str, Any]] = {}
    trace_owner: dict[str, str] = {}
    for span in store.iter_spans():
        if span.name == "invoke_agent":
            aid = span.attributes.get(GenAI.AGENT_ID)
            if not aid:
                continue
            trace_owner[span.trace_id] = aid
            agents[aid] = {
                "id": aid,
                "persona": span.attributes.get(Swarmproof.PERSONA_NAME),
                "state": span.attributes.get(Swarmproof.AGENT_STATE),
                "goal": span.attributes.get(Swarmproof.GOAL_ID),
                "misuse": span.attributes.get("swarmproof.agent.misuse", False),
            }
    for span in store.iter_spans():
        owner = trace_owner.get(span.trace_id)
        if not owner or owner not in agents:
            continue
        if span.name == "chat":
            agents[owner]["reasoning"] = span.attributes.get(Swarmproof.DECISION_REASONING)
        if span.name == "execute_tool":
            agents[owner]["tool"] = span.attributes.get(GenAI.TOOL_NAME)
    return agents


def build_app(hub: LiveHub | None = None, meta: str = "", store: TraceStore | None = None):
    """Build the dashboard FastAPI app. Pass a ``hub`` for live streaming, or a
    ``store`` for a one-shot post-run view."""
    if not _HAS_FASTAPI:  # pragma: no cover - env-dependent
        raise RuntimeError("the dashboard needs: pip install 'stampede[dashboard]'")

    app = FastAPI()

    @app.get("/")
    async def index() -> HTMLResponse:  # pragma: no cover - browser path
        return HTMLResponse(_PAGE)

    @app.websocket("/ws")
    async def ws(sock: WebSocket) -> None:
        await sock.accept()
        await sock.send_text(json.dumps({"meta": meta}))
        try:
            if hub is not None:
                for event in hub.snapshot():  # catch a late joiner up
                    await sock.send_text(json.dumps(event))
                queue = hub.subscribe()
                try:
                    while True:
                        event = await queue.get()
                        await sock.send_text(json.dumps(event))
                finally:
                    hub.unsubscribe(queue)
            elif store is not None:
                for event in _agents_from_store(store).values():
                    await sock.send_text(json.dumps(event))
        except WebSocketDisconnect:
            pass

    return app


def serve(store: TraceStore, meta: str = "", host: str = "127.0.0.1", port: int = 8080) -> None:
    """Serve the post-run swarm view (blocking). Requires the ``[dashboard]`` extra."""
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - env-dependent
        raise RuntimeError("the dashboard needs: pip install 'stampede[dashboard]'") from exc

    app = build_app(hub=None, meta=meta, store=store)
    print(f"  swarm dashboard → http://{host}:{port}  (Ctrl-C to stop)")
    uvicorn.run(app, host=host, port=port, log_level="warning")
