#!/usr/bin/env python3
"""jDaLink testserver — fase 0: tools valideren met mock-data."""
from mcp.server.mcpserver import MCPServer
from datetime import datetime, timedelta, timezone
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import os
from pathlib import Path
import json
import urllib.request
import time

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
    return rv


@mcp.tool()
def jdalog_get_lastchange(s: str) -> dict:
    """Laatste verandering van één signaal. Gebruik jdalog_list_signals voor de exacte namen."""
    with urllib.request.urlopen("http://" + conf["jDaLog_ip"] + "/in.json") as r:
        lst = json.loads(r.read())
    if s not in lst:
        return {"error": f"onbekend signaal: {s}", "known": list(lst)}
            
    with urllib.request.urlopen("http://" + conf["jDaLog_ip"] + f"/in/{s}/json/week.json") as r:
        recs = json.loads(r.read())
    lastchange = None
    lastvalue = None
    lastvalue_store = None
    for key in sorted(recs[s], key=float):
        value = recs[s][key]
        if lastvalue is None:
            lastvalue = value                  # eerste record = initialisatie, geen change
        if value != lastvalue:
            lastchange = float(key)
            lastvalue_store = lastvalue
        lastvalue = value
            
    rv = {"signal": s, "name": lst[s]["name"], "value": lst[s]["value"],
          "decimals": lst[s]["decimals"], "age": lst[s]["age"], "valid": lst[s]["valid"],
          "unit": lst[s].get("unit", "")}

    if lastchange is None:
        rv["time_lastchange"] = None
        rv["time_sincelastchange"] = None
        rv["note"] = "geen waardeverandering binnen het weekvenster"
    else:
        rv["time_lastchange"] = datetime.fromtimestamp(lastchange).astimezone().isoformat(timespec="milliseconds")
        rv["time_sincelastchange"] = time.time() - lastchange
        rv["value_beforelastchange"] = lastvalue_store

    return rv

def parse_iso(s: str) -> float:
    """ISO 8601 -> epoch seconden (float, dus fractionele seconden gratis)."""
    s = s.strip().replace("Z", "+00:00")   # 3.11+-shim; laat staan mag op ≥3.11
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:                  # naïef? dan lokale tijd van de host
        dt = dt.astimezone()              # (of expliciet: dt.replace(tzinfo=...)
    return dt.timestamp()

@mcp.tool()
def jdalog_get_summary(signals: list[str], start: str, end: str, bins: int, include_edges: bool = False) -> dict:
    """
    Summary of one or more signals side by side over the same time window.
    Use jdalog_list_signals for the exact names.
    Inputs: 
        signals - list of signal keys/descriptors (1 or more)
        start - from, start-time of the summary, ISO format.
        end - to, end-time of the summary, ISO format.
        bins - Number of bins to display in the summary.
        include_edges - Optional, result includes edge counters if set to True.
    """
    signals = [s.strip() for s in signals if s.strip()]

    with urllib.request.urlopen("http://" + conf["jDaLog_ip"] + "/in.json") as r:
        lst = json.loads(r.read())
    for signal in signals:
        if signal not in lst:
            return {"error": f"unknown signal: {signal}", "known signals": list(lst)}

    t0 = parse_iso(start);
    t1 = parse_iso(end);
    
    if t0 >= t1:
        raise ValueError(f"start ({start}) must be before end ({end})")
    if bins < 1:
        raise ValueError(f"bins must be >= 1, got {bins}")
    
    first = True
    rv = {}
    for signal in signals:
        url = "http://" + conf["jDaLog_ip"] + f"/in/{signal}/json/summary_{t0:.0f}_{t1:.0f}_{bins}.json"
        with urllib.request.urlopen(url) as r:
            j = r.read()
            recs = json.loads(j)
            if first:
                first = False
                rv = recs
            else:
                rv["signals"][signal] = recs["signals"][signal]
    
    # Translate the timestamps to ISO format. Rest of the summary format is OK.
    # Optionally removes the edge counters.
    rv["from"] = datetime.fromtimestamp(recs["from"]).astimezone().isoformat(timespec="milliseconds")
    rv["to"] = datetime.fromtimestamp(recs["to"]).astimezone().isoformat(timespec="milliseconds")
    for signal in signals:
        for b in rv["signals"][signal]["bins"]:
            b["t"] = datetime.fromtimestamp(b["t"]).astimezone().isoformat(timespec="milliseconds")
            if not include_edges:
                b.pop("pos_edge", None)
                b.pop("neg_edge", None)
                
    return rv

# app opbouwen mét middleware, dan draaien met uvicorn:
app = mcp.streamable_http_app()   # het ASGI-app van je FastMCP-server
app.add_middleware(BearerAuthMiddleware)

if __name__ == "__main__":
    #mcp.run(transport="streamable-http")  # stdio-transport: voor MCP Inspector / lokale clients
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)









