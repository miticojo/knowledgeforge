# Usa un'immagine Python minimale
FROM python:3.12-slim

# Evita di scrivere bytecode (.pyc) e abbrevia il buffer di stampa dei logs
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Installa dipendenze di sistema minime
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia i requirement prima per sfruttare lo strato di cache Docker
COPY requirements.txt .

# Installa le dipendenze Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia l'intero progetto
COPY . .

# Cloud Run inietta la porta dinamica (di solito 8080)
EXPOSE 8080

# Esegui l'app FastAPI tramite Uvicorn
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
