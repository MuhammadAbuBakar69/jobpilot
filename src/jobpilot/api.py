"""REST API over the same store the CLI uses.

    uvicorn jobpilot.api:app --reload      # or: jobpilot serve

Endpoints
    GET  /health
    GET  /applications?status=&limit=
    POST /applications          {text, use_llm?}   or a full record
    PATCH /applications/{id}    {status}
    GET  /stats
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import db
from .extract import parse_heuristic, parse_with_llm


class IngestRequest(BaseModel):
    text: str = Field(..., min_length=1, description="raw posting text")
    use_llm: bool = False


class StatusUpdate(BaseModel):
    status: str


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(
        title="jobpilot",
        version="0.1.0",
        summary="Track job applications from raw text.",
    )
    target = str(db_path or db.DEFAULT_DB)

    def get_conn() -> Iterator[sqlite3.Connection]:
        """One connection per request: sqlite objects are bound to their thread."""
        connection = db.connect(target)
        try:
            yield connection
        finally:
            connection.close()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/applications")
    def list_applications(
        status: str | None = None,
        limit: int = 50,
        conn=Depends(get_conn),  # noqa: B008 - FastAPI dependency style
    ) -> list[dict[str, Any]]:
        return db.list_applications(conn, status=status, limit=limit)

    @app.post("/applications", status_code=201)
    def create_application(payload: IngestRequest, conn=Depends(get_conn)) -> dict[str, Any]:  # noqa: B008
        posting = parse_with_llm(payload.text) if payload.use_llm else parse_heuristic(payload.text)
        new_id = db.add(conn, posting.to_dict())
        if new_id is None:
            raise HTTPException(status_code=409, detail="application already tracked")
        return {"id": new_id, **posting.to_dict()}

    @app.patch("/applications/{app_id}")
    def change_status(
        app_id: int,
        payload: StatusUpdate,
        conn=Depends(get_conn),  # noqa: B008
    ) -> dict[str, Any]:
        try:
            updated = db.update_status(conn, app_id, payload.status)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not updated:
            raise HTTPException(status_code=404, detail="application not found")
        return {"id": app_id, "status": payload.status}

    @app.get("/stats")
    def stats(conn=Depends(get_conn)) -> dict[str, Any]:  # noqa: B008
        return db.summary(conn)

    return app


app = create_app()
