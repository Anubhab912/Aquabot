FROM python:3.11-slim

# Non-root user for security
RUN useradd -m appuser

WORKDIR /app

# Cache pip layer separately from source
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run expects port 8080
EXPOSE 8080

USER appuser

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
