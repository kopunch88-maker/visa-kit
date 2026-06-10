# Pack 53 (перевод выписки) — сбор контекста для Клода
# Создаёт C:\Users\New\Desktop\pack53_dump.txt со всеми нужными файлами

$ErrorActionPreference = "SilentlyContinue"
$repo = "D:\VISA\visa_kit"
$out  = "$env:USERPROFILE\Desktop\pack53_dump.txt"

Set-Content -Path $out -Value "" -Encoding UTF8

function Add-File {
    param([string]$Path, [string]$Label = $null)
    if (-not $Label) { $Label = $Path }
    $full = if ($Path -like "*:*") { $Path } else { Join-Path $repo $Path }
    if (Test-Path $full) {
        $size = (Get-Item $full).Length
        Add-Content -Path $out -Value "" -Encoding UTF8
        Add-Content -Path $out -Value ("=" * 70) -Encoding UTF8
        Add-Content -Path $out -Value "FILE: $Label" -Encoding UTF8
        Add-Content -Path $out -Value "SIZE: $size bytes" -Encoding UTF8
        Add-Content -Path $out -Value ("=" * 70) -Encoding UTF8
        $content = Get-Content $full -Encoding UTF8 -Raw
        Add-Content -Path $out -Value $content -Encoding UTF8 -NoNewline
        Add-Content -Path $out -Value "" -Encoding UTF8
        Write-Host "OK   $Label ($size B)"
    } else {
        Write-Host "MISS $Label"
    }
}

function Add-Section {
    param([string]$Title)
    Add-Content -Path $out -Value "" -Encoding UTF8
    Add-Content -Path $out -Value ("#" * 70) -Encoding UTF8
    Add-Content -Path $out -Value "# SECTION: $Title" -Encoding UTF8
    Add-Content -Path $out -Value ("#" * 70) -Encoding UTF8
}

Add-Section "1. Translation orchestrator + директория translation/"
Get-ChildItem -Path "$repo\backend\app\services\translation" -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
    $rel = $_.FullName.Substring($repo.Length + 1)
    Add-File $rel
}

Add-Section "2. Backend файлы со словом 'translat' или 'перевод' (для понимания паттерна — особенно tech_opinion Pack 43.0)"
$seen = @{}
foreach ($p in @("$repo\backend\app\services", "$repo\backend\app\templates_engine", "$repo\backend\app\api")) {
    Get-ChildItem -Path $p -Recurse -File -Include *.py -ErrorAction SilentlyContinue |
        Select-String -Pattern "translat|перевод" -List -ErrorAction SilentlyContinue |
        ForEach-Object {
            if (-not $seen.ContainsKey($_.Path)) {
                $seen[$_.Path] = $true
                $rel = $_.Path.Substring($repo.Length + 1)
                Add-File $rel
            }
        }
}

Add-Section "3. Bank statement рендерер (docx_renderer + context)"
Add-File "backend\app\templates_engine\docx_renderer.py"
Add-File "backend\app\templates_engine\context.py"
Add-File "backend\app\templates_engine\context_bank_statement.py"
Add-File "backend\app\templates_engine\bank_statement_generator.py"

Add-Section "4. Эндпоинты выписки (POST routes)"
Get-ChildItem -Path "$repo\backend\app\api" -File -Include *.py -ErrorAction SilentlyContinue |
    Select-String -Pattern "bank_statement|render_bank|выписк" -List -ErrorAction SilentlyContinue |
    ForEach-Object {
        $rel = $_.Path.Substring($repo.Length + 1)
        Add-File $rel
    }

Add-Section "5. Application model + Pydantic"
Add-File "backend\app\models\application.py"

Add-Section "6. Все шаблоны в templates\docx\ (список — ищем bank_statement_translation* или похожие)"
Add-Content -Path $out -Value "Полный листинг templates\docx\:" -Encoding UTF8
Get-ChildItem -Path "$repo\templates\docx" -Recurse -File -ErrorAction SilentlyContinue |
    Sort-Object FullName |
    ForEach-Object {
        $rel = $_.FullName.Substring($repo.Length + 1)
        Add-Content -Path $out -Value ("  {0,8} B   {1}" -f $_.Length, $rel) -Encoding UTF8
    }

Add-Section "7. Frontend: компоненты дровера + сетки документов"
Add-File "frontend\src\components\admin\ApplicantDrawer.tsx"
Add-File "frontend\src\components\admin\DocumentsGrid.tsx"
Add-File "frontend\src\components\admin\AdminClientDocuments.tsx"
Add-File "frontend\src\components\admin\BankStatementSection.tsx"

Add-Section "8. Frontend: API client (для добавления нового endpoint)"
Add-File "frontend\lib\api.ts"
Add-File "frontend\src\lib\api.ts"

Add-Section "9. Frontend файлы со словом 'выписк' / 'bank_statement' / 'BankStatement'"
$seenFront = @{}
Get-ChildItem -Path "$repo\frontend" -Recurse -File -Include *.tsx,*.ts -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "node_modules|\.next|dist|build" } |
    Select-String -Pattern "выписк|bank_statement|BankStatement|render_bank" -List -ErrorAction SilentlyContinue |
    ForEach-Object {
        if (-not $seenFront.ContainsKey($_.Path)) {
            $seenFront[$_.Path] = $true
            $rel = $_.Path.Substring($repo.Length + 1)
            Add-File $rel
        }
    }

Add-Section "10. Frontend: API client (поиск переводных функций — getTranslation/translateDoc и пр.)"
Get-ChildItem -Path "$repo\frontend" -Recurse -File -Include *.ts,*.tsx -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "node_modules|\.next|dist|build" } |
    Select-String -Pattern "translat|перевод" -List -ErrorAction SilentlyContinue |
    Select-Object -First 10 |
    ForEach-Object {
        if (-not $seenFront.ContainsKey($_.Path)) {
            $seenFront[$_.Path] = $true
            $rel = $_.Path.Substring($repo.Length + 1)
            Add-File $rel
        }
    }

Write-Host ""
Write-Host ("=" * 70)
Write-Host "ГОТОВО"
Write-Host "Файл: $out"
$finalSize = (Get-Item $out).Length
Write-Host ("Размер: {0:N0} bytes ({1:N2} MB)" -f $finalSize, ($finalSize / 1MB))
Write-Host ("=" * 70)
