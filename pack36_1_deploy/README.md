# Pack 36.1 — TIE формы (MI-TIE + EX-17)

## Что добавляет

Две новые AcroForm PDF-формы для карты TIE:
- **15_MI-TIE.pdf** — Movilidad Internacional (Ley 14/2013, DIR3 E04931201)
- **16_EX-17.pdf** — универсальная МВД (LO 4/2000 y RD 557/2011)

Обе подаются после одобрения MI-T и получения NIE.

## Установка

```powershell
cd <папка_с_этим_pack>
PowerShell -ExecutionPolicy Bypass -File .\apply_pack36_1.ps1
```

Скрипт:
1. Покажет план изменений
2. Спросит подтверждение
3. Запустит Python patcher (SHA256 валидация + str_replace + бэкапы)
4. Проверит SHA256 после установки

## Что меняется

| Файл | Действие |
|---|---|
| `backend/app/pdf_forms_engine/render_mi_tie.py` | новый |
| `backend/app/pdf_forms_engine/render_ex17.py` | новый |
| `backend/app/pdf_forms_engine/builder.py` | замена (добавит 2 формы в ZIP) |
| `templates/pdf/MI_TIE.pdf` | новый |
| `templates/pdf/EX_17.pdf` | новый |
| `frontend/components/admin/cards/TieCard.tsx` | новый |
| `frontend/components/admin/TieDrawer.tsx` | новый |
| `backend/app/models/application.py` | +`nie` +`fingerprint_date` поля |
| `backend/app/db/migrations.py` | +`apply_pack36_1_migration` |
| `backend/app/main.py` | импорт + вызов миграции |
| `backend/app/api/applications.py` | `_DOWNLOAD_FILES` + `ApplicationPatch` + handler |
| `frontend/components/admin/ApplicationDetail.tsx` | +TieCard в сетке + state + Drawer |
| `frontend/components/admin/DocumentsGrid.tsx` | +2 строки в DOCUMENTS |
| `frontend/lib/api.ts` | +`nie?`/`fingerprint_date?` в `ApplicationResponse` (заодно убран дубль `is_paid`) |

## После установки

1. **Перезапустить backend** — миграция запустится автоматически в lifespan
2. **Перебилдить frontend**: `cd frontend && npm run build` (или dev)
3. **Открыть любую заявку** в админке → должна появиться карточка «КАРТА TIE» рядом с «ПОДАЧА»
4. **Заполнить NIE** (формат `Z3751311Q`) + **дату отпечатков** → нажать Сохранить
5. **Скачать MI-TIE** и **EX-17** через кнопки на карточке
6. **Проверить PDF на iPhone** в Telegram preview — должны быть видны все галки и текст

## Откат

Все изменённые файлы бэкапятся с timestamp:
```powershell
Get-ChildItem -Path D:\VISA\visa_kit -Recurse -Filter "*.bak_pre_pack36_1_*"
```

Чтобы откатить любой файл:
```powershell
Copy-Item file.py.bak_pre_pack36_1_20260516_xxxxxx file.py -Force
```

Новые файлы (render_mi_tie.py, render_ex17.py, MI_TIE.pdf, EX_17.pdf,
TieCard.tsx, TieDrawer.tsx) — просто удалить.

## ⚠ Если ApplicationDetail.tsx патч не применился

Patcher делает 5 точечных правок в `frontend/components/admin/ApplicationDetail.tsx`.
Если строки в файле отличаются от ожидаемых — patcher откатит правки и
выдаст ❌. Нужно сделать вручную:

1. Импорт TieCard рядом с SubmissionCard:
   ```tsx
   import { TieCard } from "./cards/TieCard";
   ```

2. Импорт TieDrawer рядом с SubmissionDrawer:
   ```tsx
   import { TieDrawer } from "./TieDrawer";
   ```

3. State:
   ```tsx
   const [showTieDrawer, setShowTieDrawer] = useState(false);
   ```

4. В сетке карточек после SubmissionCard:
   ```tsx
   <TieCard
     application={application}
     onEdit={() => setShowTieDrawer(true)}
   />
   ```

5. Рядом с другими drawer'ами:
   ```tsx
   {showTieDrawer && (
     <TieDrawer
       application={application}
       onClose={() => setShowTieDrawer(false)}
       onSaved={() => {
         setShowTieDrawer(false);
         onChanged();
       }}
     />
   )}
   ```

## SHA256 артефактов

| Файл | SHA256 |
|---|---|
| render_mi_tie.py | `4e039f2efefe8824f5658b89b8b3faf0b78ad9c991a938d0df2397fd4e2fe712` |
| render_ex17.py | `1becebadabfc0b7cf3650b06b9f99daff93f67959025746da749e898b1c51490` |
| builder.py | `be8db9d2ad336db21ace0fbaee3893e9c1f881587c59e0bdbf85d075f58a1614` |
| MI_TIE.pdf | `b90c0cc229427cfd64358fcc2953ef3bc29c4e785e67c099ed3ae7163b69380a` |
| EX_17.pdf | `d81e1d94eac3d642365485389f27367a7eb6dcae43f0622ab68cff609e467bf5` |
| TieCard.tsx | `4342d4c28681aebae924faed8c6b4af6bd70c87afa81cfdfccce38c8db560902` |
| TieDrawer.tsx | `da8ae02bcad4440a7b90383a58af2aca611cc1649f6ba4052bdbef70967d93df` |
