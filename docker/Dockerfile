# ══════════════════════════════════════════════════════
# Dockerfile — Assistant Intelligent Doc
# ══════════════════════════════════════════════════════

FROM python:3.11-slim

# Métadonnées
LABEL maintainer="ISI KOMUNIK"
LABEL description="Assistant RAG pour documentation GitHub francophone"

# Répertoire de travail
WORKDIR /app

# Variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Installation des dépendances système
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copie et installation des dépendances Python
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copie du code source
COPY . .

# Port Streamlit
EXPOSE 8501

# Lancement de l'application
CMD ["streamlit", "run", "src/app/main.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0"]