# -*- coding: utf-8 -*-
"""
Pack 37.0 — AI Document Audit service.

Симуляция приёма документов в консульстве: LLM-аудитор получает «досье»
кейса (applicant + company + 16+ сгенерированных документов + сырой OCR
оригиналов), сравнивает всё со всем и выдаёт структурированный список
несоответствий с рекомендациями по исправлению.

Модули:
- document_extractor — извлечение текста из DOCX/PDF в R2
- context_builder    — сборка «досье» для LLM
- prompts            — system prompt + чек-листы + JSON schema
- auditor            — LLM-вызов + парсинг результата (Pack 37.0-C)
- fix_handlers       — whitelist applicators для авто-фиксов (Pack 37.0-C)

Использование:
    from app.services.audit.context_builder import build_audit_context
    from app.services.audit.prompts import get_system_prompt, get_user_prompt

    ctx = build_audit_context(application_id=10, session=session)
    system = get_system_prompt()
    user = get_user_prompt(ctx.to_llm_json())
    # ... передаём в auditor (Pack 37.0-C) ...
"""

from .document_extractor import (
    extract_application_documents,
    ExtractedDocument,
    ExtractionResult,
)
from .context_builder import (
    build_audit_context,
    AuditContext,
)
from .prompts import (
    get_system_prompt,
    get_user_prompt,
    SUPPORTED_FIX_ACTIONS,
)

__all__ = [
    "extract_application_documents",
    "ExtractedDocument",
    "ExtractionResult",
    "build_audit_context",
    "AuditContext",
    "get_system_prompt",
    "get_user_prompt",
    "SUPPORTED_FIX_ACTIONS",
]
