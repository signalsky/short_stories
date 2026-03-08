FROM python:3.9-slim

WORKDIR /app

# Install system dependencies for opencv and paddlepaddle
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libgomp1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download PaddleOCR models during build to avoid download on first run
RUN python -c "from paddleocr import PaddleOCR; PaddleOCR(use_angle_cls=True, lang='ch')"

COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
