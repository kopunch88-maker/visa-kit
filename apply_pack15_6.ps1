# Pack 15.6 — починка перевода textbox-ов в DOCX (карточка реквизитов выписки + шапка операций в header).
# Изменяет: backend/app/services/translation/docx_translator.py
# Идемпотентный: повторный запуск ничего не сломает (проверяет маркер Pack 15.6 в файле).
#
# ВАЖНО: запускать из D:\VISA\visa_kit\

$ErrorActionPreference = "Stop"
$VISA_ROOT = "D:\VISA\visa_kit"

# 1. Проверки окружения
if (-not (Test-Path $VISA_ROOT)) {
    Write-Host "ERROR: $VISA_ROOT не существует. Запусти скрипт на машине с проектом." -ForegroundColor Red
    exit 1
}
Set-Location $VISA_ROOT

$TARGET = "backend\app\services\translation\docx_translator.py"
if (-not (Test-Path $TARGET)) {
    Write-Host "ERROR: $TARGET не найден. Структура проекта изменилась?" -ForegroundColor Red
    exit 1
}

# 2. Идемпотентность: проверяем уже ли применён Pack 15.6
$existing = Get-Content $TARGET -Raw -Encoding UTF8
if ($existing -match "Pack 15\.6 textbox fix") {
    Write-Host "Pack 15.6 уже применён в $TARGET — ничего не делаем." -ForegroundColor Yellow
    exit 0
}

# 3. Бэкап
$BACKUP = "$TARGET.bak_pre_pack15_6"
if (-not (Test-Path $BACKUP)) {
    Copy-Item $TARGET $BACKUP -Force
    Write-Host "Бэкап создан: $BACKUP" -ForegroundColor Green
} else {
    Write-Host "Бэкап уже существует: $BACKUP (не перезаписываю)" -ForegroundColor Yellow
}

# 4. Записываем новый файл
# Содержимое читается из docx_translator_NEW.py рядом с этим скриптом
$NEW_FILE = Join-Path $PSScriptRoot "docx_translator_NEW.py"
if (-not (Test-Path $NEW_FILE)) {
    Write-Host "ERROR: $NEW_FILE не найден. Положи docx_translator_NEW.py рядом со скриптом." -ForegroundColor Red
    exit 1
}

Copy-Item $NEW_FILE $TARGET -Force
Write-Host "Файл обновлён: $TARGET" -ForegroundColor Green

# 5. Smoke test: импорт модуля
Write-Host ""
Write-Host "Smoke test: проверяем что модуль импортируется..." -ForegroundColor Cyan
Push-Location backend
try {
    $env:PYTHONIOENCODING = "utf-8"
    & .venv\Scripts\python.exe -c "from app.services.translation.docx_translator import _collect_all_paragraphs, _iter_txbx_paragraphs, _is_inside_mc_fallback; print('Import OK: _collect_all_paragraphs, _iter_txbx_paragraphs, _is_inside_mc_fallback')"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: импорт упал. Откатываю." -ForegroundColor Red
        Pop-Location
        Copy-Item $BACKUP $TARGET -Force
        Write-Host "Откатили на $BACKUP" -ForegroundColor Yellow
        exit 1
    }
} finally {
    Pop-Location
}

# 6. Smoke test: прогоняем _collect_all_paragraphs на шаблоне выписки и считаем
#    что после фикса собирается БОЛЬШЕ параграфов чем было.
Write-Host ""
Write-Host "Smoke test: _collect_all_paragraphs на bank_statement_template.docx..." -ForegroundColor Cyan
Push-Location backend
try {
    $smokeCode = @"
from docx import Document
from app.services.translation.docx_translator import _collect_all_paragraphs

doc = Document(r'..\templates\docx\bank_statement_template.docx')
ps = _collect_all_paragraphs(doc)
unique = len({id(p._element) for p in ps})

# Pack 15.6: ожидаем >=80 уникальных параграфов (было 65 до фикса)
assert unique >= 80, f'Expected >=80 unique paragraphs after Pack 15.6 fix, got {unique}'

# Проверяем что textbox-параграфы захвачены
import re
texts = [''.join(r.text for r in p.runs).strip() for p in ps]
required = ['Номер счета', 'Дата проводки', 'Текущий счёт', 'Клиент']
for label in required:
    if not any(label in t for t in texts):
        raise AssertionError(f'Missing required label after Pack 15.6 fix: {label!r}')

print(f'OK: {len(ps)} paragraphs collected, {unique} unique, all required labels present')
"@
    & .venv\Scripts\python.exe -c $smokeCode
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: smoke упал. Откатываю." -ForegroundColor Red
        Pop-Location
        Copy-Item $BACKUP $TARGET -Force
        Write-Host "Откатили на $BACKUP" -ForegroundColor Yellow
        exit 1
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "✅ Pack 15.6 применён успешно." -ForegroundColor Green
Write-Host ""
Write-Host "Проверь руками на проде:" -ForegroundColor Cyan
Write-Host "  1. Перегенерируй выписку для любого клиента (пересоздай 10_Extracto_bancario)"
Write-Host "  2. Открой её в Word — вся карточка реквизитов и шапка операций должны быть на испанском"
Write-Host "  3. Если что-то поехало — git diff покажет ровно одно изменение в docx_translator.py"
Write-Host ""
Write-Host "Откат если нужно:" -ForegroundColor Cyan
Write-Host "  Copy-Item $BACKUP $TARGET -Force"
