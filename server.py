#!/usr/bin/env python3
"""jDaLink testserver — fase 0: tools valideren met mock-data."""
from mcp.server.mcpserver import MCPServer
from datetime import datetime, timedelta
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import os
from pathlib import Path
import json
import urllib.request

with open("config.json", "r") as f:
    conf = json.load(f)

class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {conf['Bearer']}":
            return JSONResponse(
                {"jsonrpc": "2.0", "error": {"code": -32001, "message": "Unauthorized"}},
                status_code=401,
            )
        return await call_next(request)

mcp = MCPServer("jDaLink")

# ---- tools ----
@mcp.tool()
def jdalog_list_signals() -> dict:
    """Lijst alle beschikbare signalen met naam, eenheid, decimals en actuele waarde."""
    with urllib.request.urlopen("http://" + conf["jDaLog_ip"] + "/in.json") as r:
        lst = json.loads(r.read())
    for i in lst:
        lst[i]["unit"] = lst[i].get("unit", "")
        lst[i]["time"] = datetime.fromtimestamp(lst[i]["time"]).astimezone().isoformat(timespec="milliseconds")
    rv = {"signals":lst}
    print(rv)
    return rv

@mcp.tool()
def jdalog_get_latest(s: str) -> dict:
    """Actuele waarde van één signaal. Gebruik jdalog_list_signals voor de exacte namen."""
    with urllib.request.urlopen("http://" + conf["jDaLog_ip"] + "/in.json") as r:
        lst = json.loads(r.read())
    if s not in lst:
        return {"error": f"onbekend signaal: {s}", "known": list(lst)}
    rv = {"signal": s, "name":lst[s]["name"], "value":lst[s]["value"], "decimals":lst[s]["decimals"],
            "age": lst[s]["age"], "valid": lst[s]["valid"], 
            "time": datetime.fromtimestamp(lst[s]["time"]).astimezone().isoformat(timespec="milliseconds"), 
            "unit":lst[s].get("unit", "")}

    print ( rv)
    return rv

#def parse_window(t_from: str, t_to: str):
#    """ISO 8601 of relatief ('now', '24h', 'yesterday 00:00'); default Europe/Amsterdam."""
#    # TODO fase 1: echte resolver met zoneinfo. Voor de test: naïef.
#    return datetime.fromisoformat(t_from), datetime.fromisoformat(t_to)

#@mcp.tool()
#def jdalog_duration_above(signal: str, threshold: float,
#                          t_from: str = "24h", t_to: str = "now") -> dict:
#    """Aantal seconden dat het signaal boven de threshold lag binnen het venster.
#    t_from/t_to: ISO 8601 (default-zone Europe/Amsterdam) of relatief: 'now', '24h',
#    'yesterday 00:00'. Retourneert ook het aantal flanken (aan/uit wissels)."""
#    f, t = parse_window(t_from, t_to)
#    # mock: 3 kwartier boven de drempel, 5 flanken
#    return {"signal": signal, "threshold": threshold,
#            "window": [f.isoformat(), t.isoformat()],
#            "seconds_above": 2700, "flanks": 5,
#            "note": "MOCK — nog niet aangesloten op jDaLog"}

# app opbouwen mét middleware, dan draaien met uvicorn:
app = mcp.streamable_http_app()   # het ASGI-app van je FastMCP-server
app.add_middleware(BearerAuthMiddleware)

if __name__ == "__main__":
    #mcp.run(transport="streamable-http")  # stdio-transport: voor MCP Inspector / lokale clients
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)









