"""
Oracle EBS Network Monitoring — laptop-facing endpoints.

`client_router` (any logged-in employee, mounted at /ebs-netmon-client): the
in-browser connection test an HO user runs from /dashboard/ebs-check. The
dashboard backend sits on the Plant LAN next to EBS, so a request from an HO
browser crosses exactly the HO LAN -> tunnel -> Plant path EBS traffic does;
RTT and throughput here are the same two numbers Oracle's own EBS Network
Test reports.

`agent_router` (no login, mounted at /ebs-netmon-agent): where the generated
PowerShell agent posts its summary, authorised by the one-time token baked
into the script. It can do nothing except append one laptop report.
"""
import json
import os
import time
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from app.dependencies import CurrentUser, get_current_user
from app.models.ebs_netmon import EbsNetAgentToken, EbsNetSessionLocal, get_ebsnet_db
from app.services.ebs_netmon import service
from app.services.ebs_netmon import settings as cfg

client_router = APIRouter()
agent_router = APIRouter()

NO_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}
MAX_DOWNLOAD = 10 * 1024 * 1024
MAX_UPLOAD = 10 * 1024 * 1024
MAX_AGENT_BODY = 2 * 1024 * 1024
# Random so nothing on the path (nginx gzip, FortiGate WAN optimisation) can
# compress it and inflate the measured rate. Generated once; repeating a
# 1 MiB block is still incompressible for any 32 KiB-window compressor.
_BLOCK = os.urandom(1024 * 1024)


@client_router.get("/ping")
def ping(_: CurrentUser = Depends(get_current_user)):
    return Response(content=json.dumps({"t": time.time()}), media_type="application/json", headers=NO_CACHE)


@client_router.get("/download")
def download(size: int = 2_000_000, _: CurrentUser = Depends(get_current_user)):
    size = min(max(size, 1024), MAX_DOWNLOAD)
    reps, rest = divmod(size, len(_BLOCK))
    body = _BLOCK * reps + _BLOCK[:rest]
    return Response(content=body, media_type="application/octet-stream", headers=NO_CACHE)


@client_router.post("/upload")
async def upload(request: Request, _: CurrentUser = Depends(get_current_user)):
    received = 0
    start = time.perf_counter()
    async for chunk in request.stream():
        received += len(chunk)
        if received > MAX_UPLOAD:
            raise HTTPException(413, "Terlalu besar")
    return {"received": received, "server_ms": round((time.perf_counter() - start) * 1000, 1)}


@client_router.get("/config")
def config(db=Depends(get_ebsnet_db), _: CurrentUser = Depends(get_current_user)):
    s = cfg.get_all(db)
    return {"browser_probe_url": s.get("browser_probe_url") or "", "thresholds": s["thresholds"]}


@client_router.post("/report")
def submit_report(payload: dict = Body(...), db=Depends(get_ebsnet_db),
                  user: CurrentUser = Depends(get_current_user)):
    who = user.email or user.username
    return service.save_client_report(db, service.columns_from_browser(payload, who),
                                      {**payload, "user_agent": payload.get("user_agent")})


@agent_router.post("/ingest/{token}")
async def ingest(token: str, request: Request):
    body = await request.body()
    if len(body) > MAX_AGENT_BODY:
        raise HTTPException(413, "Payload terlalu besar")
    try:
        payload = json.loads(body.decode("utf-8-sig"))
    except ValueError:
        raise HTTPException(400, "JSON tidak valid")
    if not isinstance(payload, dict) or "ping_ebs" not in payload:
        raise HTTPException(400, "Bukan summary dari agen EBS diagnostic")
    return await run_in_threadpool(_ingest, token, payload)


def _ingest(token: str, payload: dict) -> dict:
    db = EbsNetSessionLocal()
    try:
        tok = db.query(EbsNetAgentToken).filter(EbsNetAgentToken.token == token).first()
        if not tok or tok.expires_at < datetime.utcnow():
            raise HTTPException(403, "Token agen tidak valid atau kedaluwarsa — unduh ulang script dari dashboard")
        payload["_token_label"] = tok.label
        tok.uses = (tok.uses or 0) + 1
        db.commit()
        res = service.save_client_report(db, service.columns_from_agent(payload), payload)
        return {"id": res["id"], "verdict": res["verdict"], "verdict_text": res["verdict_text"], "codes": res["codes"]}
    finally:
        db.close()
