# Pack 13.0a — force rebuild 2026-04-30 21:56
# Pack 11 вЂ” Production Dockerfile РґР»СЏ Railway
# РЎРѕР±РёСЂР°РµС‚ Python 3.12 СЃ Р·Р°РІРёСЃРёРјРѕСЃС‚СЏРјРё + РєРѕРїРёСЂСѓРµС‚ РєРѕРґ

FROM python:3.12-slim

# РЎРёСЃС‚РµРјРЅС‹Рµ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё РґР»СЏ РїР°РєРµС‚РѕРІ РІСЂРѕРґРµ psycopg2 Рё С€СЂРёС„С‚РѕРІ
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

# Р Р°Р±РѕС‡Р°СЏ РґРёСЂРµРєС‚РѕСЂРёСЏ
WORKDIR /app

# РЎРЅР°С‡Р°Р»Р° requirements (РєРµС€РёСЂСѓРµС‚СЃСЏ Р»СѓС‡С€Рµ)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# РљРѕРїРёСЂСѓРµРј РєРѕРґ backend
COPY backend/ ./backend/

# РљРѕРїРёСЂСѓРµРј С€Р°Р±Р»РѕРЅС‹ DOCX Рё PDF РёР· templates/
COPY templates/ ./templates/

# РџРµСЂРµР±РёСЂР°РµРјСЃСЏ РІРЅСѓС‚СЂСЊ backend/
WORKDIR /app/backend

# Railway РїРµСЂРµРґР°С‘С‚ PORT С‡РµСЂРµР· env var
ENV PORT=8000
EXPOSE 8000

# Р—Р°РїСѓСЃРє С‡РµСЂРµР· uvicorn РІ production СЂРµР¶РёРјРµ
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1
