import os
os.environ['DATABASE_URL'] = 'postgresql://postgres:uxGVZsShKKnbOZuHyiFpEaufEAnKjYXI@switchyard.proxy.rlwy.net:34408/railway'
from sqlmodel import create_engine, Session, select
from app.models import Bank

engine = create_engine(os.environ['DATABASE_URL'])
with Session(engine) as session:
    rows = session.exec(select(Bank)).all()
    print(f'Найдено банков: {len(rows)}')
    for b in rows:
        name = getattr(b, 'name', None) or getattr(b, 'short_name', None) or '?'
        print(f"  id={b.id:3d}  bik={b.bik!r:<14}  name={name!r}")
    # Проверка специально для ТБанка
    tbank = [b for b in rows if b.bik == '044525974']
    if tbank:
        print(f'\n✓ ТБанк ЕСТЬ в БД (id={tbank[0].id})')
    else:
        print('\n✗ ТБанк НЕ найден в БД — нужно добавить')
