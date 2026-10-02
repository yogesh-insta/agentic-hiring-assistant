FROM python:3.11-slim
WORKDIR /app
ENV PYTHONPATH=/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY guardrails guardrails
COPY worker worker
CMD ["python", "-m", "worker.main"]
