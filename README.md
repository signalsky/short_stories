# Xiaohongshu Scraper & OCR Service

This project provides a system to scrape short stories and tutorials from Xiaohongshu and extract text from images using a Dockerized PaddleOCR service.

## Project Structure

- `ocr_service/`: Contains the OCR API service (FastAPI + PaddleOCR).
- `xiaohongshu/`: Contains the scraping script.
- `data/`: Output directory for scraped content (Novels, Tutorials, Deconstructions).
- `docker-compose.yml`: Defines the OCR service container.

## Setup & Usage

### 1. Start the OCR Service

The OCR service runs in a Docker container.

```bash
docker-compose up --build -d
```

This will build the image and start the service on `http://localhost:8000`.

### 2. Set up Local Environment for Scraper

A virtual environment has been created in `venv`. You need to activate it and install dependencies if you haven't already.

```powershell
# Activate venv
.\venv\Scripts\Activate.ps1

# Install dependencies (if needed)
pip install -r xiaohongshu/requirements.txt
playwright install chromium
```

### 3. Run the Scraper

Run the scraper script:

```powershell
python xiaohongshu/scraper.py
```

**Workflow:**
1. A Chrome window will open.
2. **Log in to Xiaohongshu manually.**
3. Return to the terminal and press **ENTER**.
4. The script will automatically navigate to search results, scroll, and process posts.
5. Extracted text (including OCR results) will be saved in the `data/` directory.

## Features

- **Deduplication**: Uses `history.json` to skip already processed URLs.
- **Classification**: Automatically sorts content into `小说` (Novels), `拆文` (Deconstruction), `教程` (Tutorials), or `temp`.
- **Filtering**:
  - Text posts: > 50 likes
  - Image posts: > 200 likes (OCR performed)
  - Video posts: > 1000 likes (Transcription skipped for now)
- **OCR**: High-accuracy Chinese OCR using PaddleOCR via a local API.
