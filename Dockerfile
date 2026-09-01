# ─────────────────────────────────────────
# BUILD STAGE
# ─────────────────────────────────────────
FROM python:3.11-slim

# set working directory
WORKDIR /app

# install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# install python dependencies first
# (separate layer so it caches — faster rebuilds)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy all source code
COPY . .

# create folders that need to exist
RUN mkdir -p docs vector_store/faiss_index

# expose FastAPI port
EXPOSE 8000

# start the API
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]