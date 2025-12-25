# Form Fill Agent (Browser Use + Gemini)

Local FastAPI service that:
1. Scans a form to list required fields.
2. Extracts data from Passport and G-28 PDFs (OCR fallback).
3. Fills the form using browser_use and stops for human review.

## Requirements
- Python 3.10+
- Tesseract installed and on PATH
- `GOOGLE_API_KEY` set for Gemini

## Setup
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Run
```bash
set GOOGLE_API_KEY=your_key
uvicorn app.main:app --loop asyncio
```

Open `http://127.0.0.1:8000` to upload files and start a job.

## Notes
- Uploads are stored in `./data/uploads`.
- The agent does not submit the form. Review the filled browser window and submit manually.
- If scanned PDFs are slow, reduce DPI in `app/services/ocr.py`.
