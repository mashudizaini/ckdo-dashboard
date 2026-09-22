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
    tesseract-ocr-kor \
    tesseract-ocr-osd \
    && ln -sf /usr/lib/x86_64-linux-gnu/libaio.so.1t64 /usr/lib/x86_64-linux-gnu/libaio.so.1 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
RUN pip install --upgrade pip setuptools wheel

# docling depends on torch (through docling-ibm-models), and `pip install
# torch` from PyPI resolves to the CUDA build: ~3-5GB of nvidia_* wheels plus
# triton, none of which can be used on a server with no GPU. That is what
# filled the production disk and then spent an hour downloading 423MB cuBLAS
# over a 2MB/s link. Installing the CPU build from PyTorch's own index first
# leaves the requirement already satisfied, so the resolver below never
# reaches for the CUDA variant.
#
# Deliberately unpinned: the constraint that matters is "CPU build", and
# pinning a version that a future docling raises its floor past would let pip
# quietly reinstall the CUDA wheels on top — the exact failure this prevents.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch torchvision

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Oracle Instant Client will be mounted as volume at /opt/oracle
ENV LD_LIBRARY_PATH=/opt/oracle/instantclient
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
