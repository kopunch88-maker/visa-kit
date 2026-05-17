Remove-Item patch_37_pdf_split.py
@"
import sys
import re

path1 = 'backend/app/services/rendering.py'
with open(path1, encoding='utf-8') as f:
    src1 = f.read()

m = re.search(r'def build_full_package\([^)]*\):', src1, re.DOTALL)
if not m:
    print('ERROR: sig not found'); sys.exit(1)
old_sig = m.group(0)
new_sig = old_sig.replace('):', ", kind: str = 'all'):")
src1 = src1.replace(old_sig, new_sig, 1)

anchor1 = '    status: dict[str, str] = {}\n    buffer = io.BytesIO()'
new_anchor1 = '    status: dict[str, str] = {}\n    include_docx = kind in (\'all\', \'docx\')\n    include_pdf = kind in (\'all\', \'pdf\')\n    if not include_docx:\n        filtered = []\n    buffer = io.BytesIO()'
if anchor1 not in src1:
    print('ERROR: buffer anchor not found'); sys.exit(1)
src1 = src1.replace(anchor1, new_anchor1, 1)
src1 = src1.replace('if include_pdf_forms:', 'if include_pdf_forms and include_pdf:')
with open(path1, 'w', encoding='utf-8') as f:
    f.write(src1)
print('[1] OK rendering.py')

path2 = 'backend/app/api/render_endpoints.py'
with open(path2, encoding='utf-8') as f:
    src2 = f.read()

anchor2 = '@router.post("/{app_id}/render-package")'
insert2 = '''@router.post("/{app_id}/render-package-pdf")
def render_package_pdf(
    app_id: int,
    db: Session = Depends(get_session),
    _: str = Depends(require_manager),
):
    application = db.get(Application, app_id)
    if not application:
        raise HTTPException(status_code=404, detail="Not found")
    zip_bytes, status = build_full_package(application, db, kind="pdf")
    if not zip_bytes:
        raise HTTPException(status_code=500, detail="PDF package empty")
    download_name = f"pdf_forms_{application.reference}.zip"
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={download_name}"},
    )


'''
if anchor2 not in src2:
    print('ERROR: anchor2 not found'); sys.exit(1)
src2 = src2.replace(anchor2, insert2 + anchor2, 1)
src2 = src2.replace('zip_bytes, status = build_full_package(application, db)', "zip_bytes, status = build_full_package(application, db, kind='docx')")
with open(path2, 'w', encoding='utf-8') as f:
    f.write(src2)
print('[2] OK render_endpoints.py')

path3 = 'frontend/components/admin/DocumentsGrid.tsx'
with open(path3, encoding='utf-8') as f:
    src3 = f.read()

anchor3 = 'const DOCUMENTS: DocItem[] = ['
insert3 = '''const DOCX_DOCS: DocItem[] = [
  { id: "contract",            filename: "01_Dogovor.docx",           kind: "docx" },
  { id: "act_1",               filename: "02_Akt_1.docx",             kind: "docx" },
  { id: "act_2",               filename: "03_Akt_2.docx",             kind: "docx" },
  { id: "act_3",               filename: "04_Akt_3.docx",             kind: "docx" },
  { id: "invoice_1",           filename: "05_Schet_1.docx",           kind: "docx" },
  { id: "invoice_2",           filename: "06_Schet_2.docx",           kind: "docx" },
  { id: "invoice_3",           filename: "07_Schet_3.docx",           kind: "docx" },
  { id: "employer_letter",     filename: "08_Pismo.docx",             kind: "docx" },
  { id: "cv",                  filename: "09_Rezyume.docx",           kind: "docx" },
  { id: "bank_statement",      filename: "10_Vypiska.docx",           kind: "docx" },
  { id: "npd_certificate",     filename: "15_Spravka_NPD.docx",       kind: "docx" },
  { id: "npd_certificate_lkn", filename: "15b_Spravka_NPD_LKN.docx", kind: "docx" },
  { id: "apostille",           filename: "16_Apostil.docx",           kind: "docx" },
];

const PDF_DOCS: DocItem[] = [
  { id: "mi_t",        filename: "11_MI-T.pdf",                      kind: "pdf" },
  { id: "designacion", filename: "12_Designacion_representante.pdf", kind: "pdf" },
  { id: "compromiso",  filename: "13_Compromiso_RETA.pdf",           kind: "pdf" },
  { id: "declaracion", filename: "14_Declaracion_antecedentes.pdf",  kind: "pdf" },
];

'''
if anchor3 not in src3:
    print('ERROR: anchor3 not found'); sys.exit(1)
src3 = src3.replace(anchor3, insert3 + anchor3, 1)
with open(path3, 'w', encoding='utf-8') as f:
    f.write(src3)
print('[3] OK DocumentsGrid.tsx')
print('Готово')
"@ | Out-File -FilePath patch_37.py -Encoding UTF8
python patch_37.py