FROM python:3.11-slim

# System dependencies for opencv, easyocr, ffmpeg, audio libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    libglib2.0-0 \
    libsndfile1 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create uploads directory
RUN mkdir -p uploads/incidents uploads/tenants

EXPOSE 5020

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5020"]
