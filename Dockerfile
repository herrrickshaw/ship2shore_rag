FROM python:3.12-slim

WORKDIR /app

# Only what api.py + ops/ actually need — not sentence-transformers/torch,
# which the RAG ingestion side pulls in but this container doesn't use.
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY ops/ ops/
COPY config.py api.py ./

EXPOSE 8010
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8010"]
