"""
Pack 40.0 — POST /admin/applications/{id}/render-tech-opinion

Рендерит Техническое заключение (DOCX) и возвращает как application/octet-stream.
Не сохраняет в БД (GeneratedDocument) — это вспомогательный документ, не финальный.
"""

from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlmodel import Session

from app.db.session import get_session
from app.models import Application
from app.templates_engine.docx_renderer import render_tech_opinion

router = APIRouter(prefix="/admin/applications", tags=["tech_opinion"])


@router.post("/{application_id}/render-tech-opinion")
def render_tech_opinion_endpoint(
    application_id: int,
    session: Session = Depends(get_session),
):
    application = session.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if not application.position_id:
        raise HTTPException(
            status_code=422,
            detail="У заявки не назначена должность — невозможно сгенерировать tech_opinion",
        )

    try:
        docx_bytes = render_tech_opinion(application, session)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Render failed: {exc}") from exc

    filename = f"tech_opinion_{application.reference}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
