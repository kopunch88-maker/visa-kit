"""
Pack 40.0 — POST /admin/applications/{id}/render-tech-opinion

Рендерит Техническое заключение (DOCX) и возвращает как application/octet-stream.
Не сохраняет в БД (GeneratedDocument) — это вспомогательный документ, не финальный.

Pack 40.0-E: автогенерация outgoing_number и outgoing_date при первом рендере.
"""

from __future__ import annotations
import re
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlmodel import Session, select

from app.db.session import get_session
from app.models import Application
from app.templates_engine.docx_renderer import render_tech_opinion

router = APIRouter(prefix="/admin/applications", tags=["tech_opinion"])


def _ensure_outgoing_fields(application: Application, session: Session) -> bool:
    """
    Pack 40.0-E: если outgoing_number IS NULL — генерируем как
    MAX(employer_letter_number у этой company) + 1 формата {N}/{YYYY}.
    outgoing_date = today() при первом рендере.

    Возвращает True если поля были изменены и сохранены в БД.
    """
    if application.outgoing_number and application.outgoing_date:
        return False

    changed = False

    if not application.outgoing_number:
        # Берём максимальный employer_letter_number у заявок этой company
        stmt = select(Application.employer_letter_number).where(
            Application.company_id == application.company_id,
            Application.employer_letter_number.is_not(None),
        )
        all_letter_nums = session.exec(stmt).all()

        max_n = 0
        for raw in all_letter_nums:
            if raw is None:
                continue
            # Принимаем форматы: "544", "544/2025", "544-EL", "EL-544/2025" и т.п.
            m = re.search(r"(\d+)", str(raw))
            if m:
                try:
                    n = int(m.group(1))
                    if n > max_n:
                        max_n = n
                except ValueError:
                    pass

        next_n = max_n + 1
        year = date.today().year
        application.outgoing_number = f"{next_n}/{year}"
        changed = True

    if not application.outgoing_date:
        application.outgoing_date = date.today()
        changed = True

    if changed:
        session.add(application)
        session.commit()
        session.refresh(application)

    return changed


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

    if not application.company_id:
        raise HTTPException(
            status_code=422,
            detail="У заявки не назначена компания — невозможно сгенерировать tech_opinion",
        )

    # Pack 40.0-E: автогенерация outgoing_number и outgoing_date при первом рендере
    _ensure_outgoing_fields(application, session)

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
