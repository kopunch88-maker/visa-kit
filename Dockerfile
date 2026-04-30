# Pack 11 — Production Dockerfile для Railway
# Собирает Python 3.12 с зависимостями + копирует код

FROM python:3.12-slim

# Системные зависимости для пакетов вроде psycopg2 и шрифтов
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Сначала requirements (кешируется лучше)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код backend
COPY backend/ ./backend/

# Копируем шаблоны DOCX и PDF из templates/
COPY templates/ ./templates/

# Перебираемся внутрь backend/
WORKDIR /app/backend

# Railway передаёт PORT через env var
ENV PORT=8000
EXPOSE 8000

# Запуск через uvicorn в production режиме
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1
