"""Deploy smoke stub of the Side notifications service (NOT the real services/notifications)."""

from fastapi import FastAPI, Request

app = FastAPI(title="Side notifications (deploy stub)")
received: list[dict] = []


@app.get("/health")
def health():
    return {"status": "ok", "version": "deploy-stub", "events_received": len(received)}


@app.post("/api/v1/devices", status_code=201)
async def register_device(request: Request):
    return await request.json()


@app.post("/internal/run-events", status_code=202)
async def run_events(request: Request):
    received.append(await request.json())
    return {"accepted": True}
