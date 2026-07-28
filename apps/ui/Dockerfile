FROM python:3.11-slim

LABEL org.opencontainers.image.title="DeskFleet Support Console" \
      org.opencontainers.image.description="Streamlit chat console for DeskFleet — paste a ticket, watch the Classifier/Researcher/Responder/Reviewer agents resolve it live." \
      org.opencontainers.image.source="https://github.com/sinalkar/deskfleet" \
      org.opencontainers.image.authors="Sanjay Sinalkar"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY assets/ ./assets/

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
