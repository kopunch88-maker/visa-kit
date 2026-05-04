"""
Эндпоинты для рендеринга пакета документов.
Pack 18.3: добавлен rendering для npd_certificate (Справка о постановке на учёт самозанятого, КНД 1122035).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
import io

from sqlmodel import Session

from app.db.session import get_session
from app.models import Application
from app.services.rendering import build_full_package
from app.templates_engine import (
    render_contract, render_act, render_invoice,
    render_employer_letter, render_cv,
    render_npd_certificate,  # Pack 18.3
    render_npd_certificate_lkn,  # Pack 18.3.3
    render_apostille,  # Pack 18.9
)
from .dependencies import require_manager

router = APIRouter(prefix="/admin/applications", tags=["render"])


@router.post("/{app_id}/render-package")
def render_full_package(
    app_id: int,
    include_bank_statement: bool = Query(
        False,
        description="Include bank statement in package. Default False until template is ready.",
    ),
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
):
    """
    Собирает полный пакет документов в ZIP и возвращает на скачивание.

    Внутри ZIP:
        01_Договор.docx
        02_Акт_1.docx ... 04_Акт_3.docx
        05_Счет_1.docx ... 07_Счет_3.docx
        08_Письмо_от_компании.docx
        09_Резюме.docx
        10_Выписка_по_счету.docx (только если include_bank_statement=True
                                  и шаблон выписки готов)

    Если каких-то шаблонов не хватает — они пропускаются. Список статусов
    рендера в заголовке ответа X-Render-Status.
    """
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(404, "Application not found")

    problems = application.validate_business_rules()
    if problems:
        raise HTTPException(
            422,
            detail={"problems": problems, "message": "Application has validation issues"},
        )

    zip_bytes, status = build_full_package(
        application, session, include_bank_statement=include_bank_statement,
    )

    if not zip_bytes:
        raise HTTPException(500, detail={"message": "Failed to render any document", "status": status})

    download_name = f"visa_package_{application.reference}.zip"
    status_str = ",".join(f"{k}={v}" for k, v in status.items())

    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"',
            "X-Render-Status": status_str,
        },
    )


@router.post("/{app_id}/render/{document_type}")
def render_single_document(
    app_id: int,
    document_type: str,
    session: Session = Depends(get_session),
    _user=Depends(require_manager),
):
    """
    Рендерит один документ.

    document_type:
        - 'contract'
        - 'act_1', 'act_2', 'act_3'
        - 'invoice_1', 'invoice_2', 'invoice_3'
        - 'employer_letter'
        - 'cv'
        - 'bank_statement'
        - 'npd_certificate'  (Pack 18.3 — справка о постановке на учёт самозанятого, КНД 1122035, формат МФЦ)
        - 'npd_certificate_lkn'  (Pack 18.3.3 — тот же документ в формате ЛКН с электронной подписью ФНС внизу)
        - 'apostille'  (Pack 18.9 — апостиль к справке НПД)
    """
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(404, "Application not found")

    try:
        if document_type == "contract":
            content = render_contract(application, session)
            filename = "Договор.docx"
        elif document_type.startswith("act_"):
            seq = int(document_type.split("_")[1])
            content = render_act(application, session, seq)
            filename = f"Акт_{seq}.docx"
        elif document_type.startswith("invoice_"):
            seq = int(document_type.split("_")[1])
            content = render_invoice(application, session, seq)
            filename = f"Счет_{seq}.docx"
        elif document_type == "employer_letter":
            content = render_employer_letter(application, session)
            filename = "Письмо_от_компании.docx"
        elif document_type == "cv":
            content = render_cv(application, session)
            filename = "Резюме.docx"
        elif document_type == "npd_certificate":
            # Pack 18.3 — справка о постановке на учёт самозанятого (КНД 1122035)
            content = render_npd_certificate(application, session)
            filename = "Справка_НПД.docx"
        elif document_type == "npd_certificate_lkn":
            # Pack 18.3.3 — тот же документ в формате ЛКН (электронная подпись ФНС внизу)
            content = render_npd_certificate_lkn(application, session)
            filename = "Справка_НПД_ЛКН.docx"
        elif document_type == "apostille":
            # Pack 18.9 — апостиль к справке НПД
            content = render_apostille(application, session)
            filename = "Апостиль.docx"
        elif document_type == "bank_statement":
            from app.templates_engine import render_bank_statement
            content = render_bank_statement(application, session)
            filename = "Выписка_по_счету.docx"
        else:
            raise HTTPException(400, f"Unknown document type: {document_type}")
    except FileNotFoundError as e:
        raise HTTPException(404, f"Template not found: {e}")
    except ValueError as e:
        raise HTTPException(422, str(e))

    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
