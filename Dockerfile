FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Avval faqat requirements — kod o'zgarganda kutubxonalar qayta o'rnatilmaydi.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY manage.py .

# SQLite fayli va eksportlar uchun
RUN mkdir -p /data && useradd -m -u 10001 tabel && chown -R tabel:tabel /app /data
USER tabel

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
