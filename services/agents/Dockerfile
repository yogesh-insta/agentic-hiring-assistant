FROM python:3.11-slim
WORKDIR /app
ENV PYTHONPATH=/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agents agents
COPY guardrails guardrails
COPY worker worker
COPY services services
COPY workflow workflow
COPY evals/cassettes evals/cassettes
COPY data/synthetic data/synthetic
EXPOSE 8090
CMD ["python", "-m", "services.agents.main"]
