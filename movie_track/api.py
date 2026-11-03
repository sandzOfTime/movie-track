import logging
import os
import secrets
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException
from .alerts import alert
from .db import Database
from .ingest import ingest
from .models import AlertRequest, ImportRequest

app = FastAPI(title="Movie Track")
logger = logging.getLogger(__name__)


def authorize(authorization: str = Header(default="")):
    token = os.getenv("MOVIE_TRACK_API_TOKEN")
    if not token:
        raise HTTPException(503, "Set MOVIE_TRACK_API_TOKEN to enable API access")
    if not secrets.compare_digest(authorization, f"Bearer {token}"):
        raise HTTPException(401, "Invalid bearer token")


def database():
    return Database(str(Path(os.getenv("MOVIE_TRACK_DATA", "var")) / "movies.sqlite3"))


def run(operation):
    try:
        return operation()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        logger.error("Operation failed (%s)", type(exc).__name__)
        raise HTTPException(502, "Provider or storage operation failed; check configuration") from exc


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/listings/import", dependencies=[Depends(authorize)])
def import_listings(request: ImportRequest):
    return run(lambda: ingest(database(), request))


@app.get("/listings", dependencies=[Depends(authorize)])
def listings():
    return run(lambda: database().latest())


@app.post("/alerts/check", dependencies=[Depends(authorize)])
def check_alerts(request: AlertRequest):
    return run(lambda: alert(database(), request))
