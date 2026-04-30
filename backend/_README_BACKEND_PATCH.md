"""
Pack 8 backend patch — корректировки для совместимости с D-фронтом.

Изменения:
1. ApplicationCreate.applicant_email становится опциональным
   (на этапе создания клиент может быть ещё не известен, менеджер просто
    делает заявку и потом вручную отправляет ссылку клиенту в Telegram)

2. ApplicationCreate получает опциональное поле submission_date
   (менеджер сразу указывает планируемую дату подачи)

3. ApplicationAssign:
   - contract_end_date становится опциональным
   - добавляется submission_date (опционально) — для удобства задавать на том же экране
   - добавляется payments_period_months (опционально, default 3)

4. Функции _enrich возвращают dict (не ApplicationRead) — чтобы Pydantic
   не валидировал None-поля во время постепенного заполнения.

Применить:
- Скопировать этот файл в app/api/applications.py поверх существующего
- Скопировать application.py в app/models/application.py поверх существующего
"""

# Этот файл служит документацией. Реальные изменения в:
# - app/models/application.py (новые схемы)
# - app/api/applications.py (использование новых схем + dict response)
