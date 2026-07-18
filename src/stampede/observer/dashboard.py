"""The watchable dashboard (FR-OB-03) — swarm view + per-agent inspector.

v0.1 scaffold: after a run, ``serve()`` starts a small FastAPI app that renders the
swarm (agents as dots, colored by terminal state), streams the trace store's spans
over a WebSocket, and answers "why did you call X?" from each agent's
``swarmproof.decision.reasoning`` span. Live-*during*-run streaming rides the same
WebSocket and lands fully in a later pass. Requires the ``[dashboard]`` extra.
"""

from __future__ import annotations

import json
from typing import Any

from stampede.trace.schema import GenAI, Swarmproof
from stampede.trace.store import TraceStore

_PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>stampede — swarm</title>
<style>
 body{margin:0;background:#1b1712;color:#faf6f0;font:14px system-ui}
 header{padding:14px 20px;border-bottom:3px solid #6b1f2a}
 h1{margin:0;font-size:18px} small{color:#b89}
 #swarm{display:flex;flex-wrap:wrap;gap:6px;padding:20px;max-width:1100px}
 .dot{width:16px;height:16px;border-radius:50%;background:#8f2d3b;cursor:pointer;opacity:.85}
 .dot.DONE{background:#2f7d4f} .dot.FAILED{background:#b03030}
 .dot.misuse{box-shadow:0 0 0 2px #b8860b}
 #inspector{position:fixed;right:0;top:0;width:340px;height:100%;background:#241d17;
   border-left:1px solid #3a2f26;padding:20px;overflow:auto;font-size:13px}
 .k{color:#b89;text-transform:uppercase;font-size:10px;letter-spacing:.08em;margin-top:12px}
 code{color:#e9b}
</style></head><body>
<header><h1>stampede · the swarm <small id=meta></small></h1></header>
<div id=swarm></div>
<div id=inspector><div class=k>inspector</div><div id=idet>click an agent…</div></div>
<script>
let agents={};
function draw(){const s=document.getElementById('swarm');s.innerHTML='';
 for(const id of Object.keys(agents).sort()){const a=agents[id];
  const d=document.createElement('div');d.className='dot '+(a.state||'')+(a.misuse?' misuse':'');
  d.title=id;d.onclick=()=>show(id);s.appendChild(d);}}
function show(id){const a=agents[id];document.getElementById('idet').innerHTML=
 `<b>${id}</b><div class=k>persona</div>${a.persona}<div class=k>state</div>${a.state}`+
 `<div class=k>goal</div>${a.goal||''}<div class=k>called</div><code>${a.tool||'—'}</code>`+
 `<div class=k>why did you call X?</div>${a.reasoning||''}`+
 `<div class=k>misuse</div>${a.misuse}`;}
const ws=new WebSocket(`ws://${location.host}/ws`);
ws.onmessage=e=>{const m=JSON.parse(e.data);
 if(m.meta){document.getElementById('meta').textContent='· '+m.meta;return;}
 agents[m.id]=Object.assign(agents[m.id]||{},m);draw();};
</script></body></html>"""


def _agents_from_store(store: TraceStore) -> dict[str, dict[str, Any]]:
    agents: dict[str, dict[str, Any]] = {}
    for span in store.iter_spans():
        a = span.attributes
        aid = a.get(GenAI.AGENT_ID)
        if span.name == "invoke_agent" and aid:
            agents.setdefault(aid, {"id": aid})
            agents[aid].update(
                persona=a.get(Swarmproof.PERSONA_NAME),
                state=a.get(Swarmproof.AGENT_STATE),
                goal=a.get(Swarmproof.GOAL_ID),
                misuse=a.get("swarmproof.agent.misuse", False),
            )
    # second pass: reasoning + realized tool live on chat/execute_tool spans; map by trace
    trace_owner: dict[str, str] = {}
    for span in store.iter_spans():
        if span.name == "invoke_agent":
            aid = span.attributes.get(GenAI.AGENT_ID)
            if aid:
                trace_owner[span.trace_id] = aid
    for span in store.iter_spans():
        owner = trace_owner.get(span.trace_id)
        if not owner:
            continue
        if span.name == "chat":
            agents[owner]["reasoning"] = span.attributes.get(Swarmproof.DECISION_REASONING)
        if span.name == "execute_tool":
            agents[owner]["tool"] = span.attributes.get(GenAI.TOOL_NAME)
    return agents


def serve(store: TraceStore, meta: str = "", host: str = "127.0.0.1", port: int = 8080) -> None:
    """Start the dashboard (blocking). Requires the ``[dashboard]`` extra."""
    try:
        import uvicorn
        from fastapi import FastAPI, WebSocket
        from fastapi.responses import HTMLResponse
    except ImportError as exc:  # pragma: no cover - env-dependent
        raise RuntimeError(
            "the live dashboard needs: pip install 'stampede[dashboard]'"
        ) from exc

    app = FastAPI()
    agents = _agents_from_store(store)

    @app.get("/")
    async def index() -> HTMLResponse:  # pragma: no cover - browser path
        return HTMLResponse(_PAGE)

    @app.websocket("/ws")
    async def ws(sock: WebSocket) -> None:  # pragma: no cover - browser path
        await sock.accept()
        await sock.send_text(json.dumps({"meta": meta}))
        for agent in agents.values():
            await sock.send_text(json.dumps(agent))

    print(f"  swarm dashboard → http://{host}:{port}  (Ctrl-C to stop)")
    uvicorn.run(app, host=host, port=port, log_level="warning")
