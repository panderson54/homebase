FROM python:3.11-slim

RUN useradd --create-home --uid 1000 appuser
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY migrations/ migrations/
COPY run.py entrypoint.sh ./

RUN mkdir -p data/uploads logs && chown -R appuser:appuser /app
USER appuser

RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
