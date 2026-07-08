FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libc6-dev \
    curl \
    ffmpeg \
    libaio1t64 \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-ind \
    && ln -sf /usr/lib/x86_64-linux-gnu/libaio.so.1t64 /usr/lib/x86_64-linux-gnu/libaio.so.1 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
RUN pip install --upgrade pip setuptools wheel

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Oracle Instant Client will be mounted as volume at /opt/oracle
ENV LD_LIBRARY_PATH=/opt/oracle/instantclient

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
