"""
Pack 40.0-G — DEPRECATED.

Этот endpoint УСТАРЕЛ. tech_opinion теперь рендерится через общий реестр:
    POST /api/admin/applications/{app_id}/render/tech_opinion

Старый POST /api/admin/applications/{app_id}/render-tech-opinion удалён.
Файл оставлен как пустой router для обратной совместимости с main.py.
"""
from fastapi import APIRouter

router = APIRouter()
