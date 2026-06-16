# -*- coding: utf-8 -*-
"""
cita_worker.py — внутренний API для воркера-ловца сит (Pack 56.5).

Машинная авторизация по общему токену CITA_WORKER_TOKEN (env), как cron-токен npd_pool_admin.
  GET  /api/internal/cita/queue   — активные «спеки на отлов»
  POST /api/internal/cita/result  — воркер репортит событие/результат
"""
import os
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db.session import get_session
from app.models import Application, Applicant
from app.models.application import ApplicationStatus
from app.pdf_forms_engine.countries_es import COUNTRY_NAMES_ES

router = APIRouter(prefix="/internal/cita", tags=["cita-worker"])

# trámites TIE-потока (порядок = приоритет). Совпадает с конфигом исходного бота.
DEFAULT_TRAMITES = [
    "POLICIA - TOMA DE HUELLAS (EXPEDICION DE TARJETA) Y RENOVACION DE TARJETA DE LARGA DURACION",
    "POLICIA - RECOGIDA DE TARJETA DE IDENTIDAD DE EXTRANJERO (TIE)",
]
SCOUT_PROVINCES = ["Madrid", "Barcelona"]


def require_worker_token(x_cita_token: Optional[str] = Header(None)) -> None:
    expected = os.getenv("CITA_WORKER_TOKEN", "").strip()
    if not expected:
        raise HTTPException(503, "CITA_WORKER_TOKEN not configured")
    if not x_cita_token or x_cita_token.strip() != expected:
        raise HTTPException(401, "invalid cita worker token")


def _nationality_es(iso: Optional[str]) -> Optional[str]:
    if not iso:
        return None
    name = COUNTRY_NAMES_ES.get(iso.upper())
    return name.upper() if name else None


def _full_name(a: Applicant) -> str:
    first = (a.first_name_latin or "").strip()
    last = (a.last_name_latin or "").strip()
    return (first + " " + last).strip().upper()


class CitaSpec(BaseModel):
    application_id: int
    reference: str
    applicant_id: int
    nie: str
    full_name: str
    birth_year: Optional[int]
    nationality_es: Optional[str]
    email: str
    phone: str
    priority_province: str
    fill_type: str
    tramites: List[str]


class CitaConfig(BaseModel):
    scout_provinces: List[str]
    redirect_enabled: bool  # глобально вкл (Pack 56.x); per-client флаг — Phase 2


class QueueResponse(BaseModel):
    config: CitaConfig
    specs: List[CitaSpec]


@router.get("/queue", response_model=QueueResponse,
            dependencies=[Depends(require_worker_token)])
def get_queue(session: Session = Depends(get_session)):
    apps = session.exec(
        select(Application).where(Application.status == ApplicationStatus.APPROVED)
    ).all()

    specs: List[CitaSpec] = []
    for app_row in apps:
        if app_row.deleted_at is not None:
            continue
        if not app_row.applicant_id:
            continue
        appl = session.get(Applicant, app_row.applicant_id)
        if not appl or not getattr(appl, "cita_catching", False):
            continue
        nie = (app_row.nie or "").strip()
        email = (getattr(appl, "cita_email", None) or "").strip()
        phone = (getattr(appl, "cita_phone", None) or "").strip()
        province = (getattr(appl, "cita_location", None) or "").strip()
        if not (nie and email and phone and province):
            continue  # неполные данные — не берём в работу
        specs.append(CitaSpec(
            application_id=app_row.id,
            reference=app_row.reference,
            applicant_id=appl.id,
            nie=nie,
            full_name=_full_name(appl),
            birth_year=(appl.birth_date.year if appl.birth_date else None),
            nationality_es=_nationality_es(getattr(appl, "nationality", None)),
            email=email,
            phone=phone,
            priority_province=province,
            fill_type=(getattr(appl, "cita_fill_type", None) or "no_cert"),
            tramites=DEFAULT_TRAMITES,
        ))

    return QueueResponse(
        config=CitaConfig(scout_provinces=SCOUT_PROVINCES, redirect_enabled=True),
        specs=specs,
    )


class CitaResultIn(BaseModel):
    application_id: int
    event: str  # slot_found | office_picked | booked | other_offices | error
    office: Optional[str] = None
    appointment_at: Optional[str] = None
    justificante_url: Optional[str] = None
    message: Optional[str] = None


@router.post("/result", dependencies=[Depends(require_worker_token)])
def post_result(payload: CitaResultIn, session: Session = Depends(get_session)):
    app_row = session.get(Application, payload.application_id)
    if not app_row or not app_row.applicant_id:
        raise HTTPException(404, "application or applicant not found")
    appl = session.get(Applicant, app_row.applicant_id)
    if not appl:
        raise HTTPException(404, "applicant not found")

    appl.cita_status = payload.event[:24]
    appl.cita_status_at = datetime.utcnow().isoformat(timespec="seconds")[:32]
    if payload.message:
        appl.cita_result_note = payload.message[:512]
    if payload.office:
        appl.cita_office = payload.office[:128]
    if payload.appointment_at:
        appl.cita_appointment_at = payload.appointment_at[:64]
    if payload.event == "booked":
        appl.cita_catching = False  # поймали ситу — выключаем отлов

    session.add(appl)
    session.commit()
    return {"ok": True, "applicant_id": appl.id, "status": appl.cita_status}
