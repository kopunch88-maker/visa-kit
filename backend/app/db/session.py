"""
Соединение с БД и dependency для FastAPI.

В разработке по умолчанию используется SQLite (один файл dev.db).
В продакшене подставится Postgres через DATABASE_URL.

API кода одинаковый — спасибо SQLModel/SQLAlchemy.
"""

from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings


# SQLite требует особой настройки connect_args для работы в многопоточном FastAPI.
# Postgres такого не требует.
connect_args: dict = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    echo=False,  # выставить True если нужно видеть SQL в консоли
    connect_args=connect_args,
)


def init_db() -> None:
    """
    Создаёт таблицы из моделей. Вызывается из main.py при старте.

    В продакшене вместо этого используется alembic upgrade head.
    Для локальной разработки create_all достаточно — быстро и просто.
    """
    # Импортируем все модели, чтобы SQLModel.metadata знал о них
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """
    Dependency для FastAPI эндпоинтов.

    Использование:
        @router.get("/foo")
        def get_foo(session: Session = Depends(get_session)):
            ...

    Сессия автоматически коммитится при успехе и откатывается при исключении.
    """
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
