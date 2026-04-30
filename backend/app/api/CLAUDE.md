# api/ — HTTP endpoints

В этой папке — FastAPI роутеры. Каждая сущность — свой файл с CRUD.

## Соглашения

### Структура файла

Каждый роутер организован одинаково:

```python
router = APIRouter(prefix="/<entities>", tags=["<entities>"])

# CRUD operations (in this exact order):
@router.get("")              # list
@router.get("/{id}")         # detail
@router.post("")             # create
@router.patch("/{id}")       # update
@router.delete("/{id}")      # delete (soft, sets is_active=False)
```

### Авторизация

- Все эндпоинты `/api/admin/*` — требуют JWT, валидируется в `dependencies.py`
- Эндпоинты `/api/client/{token}/*` — авторизуются по токену в URL,
  не требуют JWT (это и есть способ доступа клиента в кабинет)
- Эндпоинты `/api/public/*` — без авторизации (например, health check)

### Запросы и ответы

- Запросы (POST/PATCH) — модель `<Entity>Create` или `<Entity>Update` из `models/`
- Ответы — `<Entity>Read` (никогда не возвращай напрямую табличную модель — она
  может содержать internal поля)
- Списки — оборачиваем в `PaginatedResponse[<Entity>Read]` (см. `_pagination.py`)

### Обработка ошибок

Не пишем try/except в эндпоинтах. Используем HTTPException с правильным статусом:

```python
if not company:
    raise HTTPException(404, "Company not found")
if not user.has_permission(action):
    raise HTTPException(403, "Forbidden")
```

Бизнес-валидация (нарушение бизнес-правил) — статус 422, тело — список проблем:

```python
problems = application.validate_business_rules()
if problems:
    raise HTTPException(422, detail={"problems": problems})
```

### Транзакции

В FastAPI dependency `get_session` уже открывает транзакцию. Не вызывайте
`session.commit()` и `session.rollback()` вручную в эндпоинтах — это сделает
middleware. Используйте `session.add()` и `session.flush()` если нужен id до
коммита.

## Образцовые файлы

Когда нужно добавить новый CRUD для справочника — копируй `companies.py`
целиком и замени Company на свой entity. Все паттерны там уже правильные.

Когда нужен сложный workflow (как у Application — со статусами и переходами) —
смотри `applications.py`, там этот паттерн.
