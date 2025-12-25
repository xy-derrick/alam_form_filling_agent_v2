import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models.schemas import CreateJobRequest, JobResult, JobStatus, UploadResponse
from app.services.agent import scan_and_fill_form
from app.services.jobs import JobStore
from app.services.llm import build_llm
from app.services.json_log import save_text_log
from app.services.ocr import extract_passport_text, extract_pdf_text
from app.services.storage import save_uploads


if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="Form Fill Agent")
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("form_fill_agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dir = Path("frontend")
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

job_store = JobStore()
uploads_index: Dict[str, Dict[str, str]] = {}


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    index_path = frontend_dir / "index.html"
    return FileResponse(index_path)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/api/uploads", response_model=UploadResponse)
async def upload_files(
    passport: UploadFile = File(...),
    g28: UploadFile = File(...),
) -> UploadResponse:
    logger.info("Upload requested: passport=%s, g28=%s", passport.filename, g28.filename)
    upload_id, files = save_uploads(passport, g28)
    logger.info("Upload saved: upload_id=%s", upload_id)
    uploads_index[upload_id] = files
    return UploadResponse(upload_id=upload_id, files=files)


@app.post("/api/jobs")
async def create_job(request: CreateJobRequest) -> dict:
    if not settings.google_api_key:
        logger.error("GOOGLE_API_KEY not set; cannot start job")
        raise HTTPException(status_code=400, detail="GOOGLE_API_KEY is not set")

    files = uploads_index.get(request.upload_id)
    if not files:
        logger.error("Upload not found: upload_id=%s", request.upload_id)
        raise HTTPException(status_code=404, detail="Upload not found")

    logger.info("Creating job for upload_id=%s form_url=%s", request.upload_id, request.form_url)
    job = await job_store.create(request.upload_id, request.form_url, files)
    asyncio.create_task(_run_job(job.job_id))
    return {"job_id": job.job_id}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    view = await job_store.view(job_id)
    if not view:
        logger.warning("Job not found: job_id=%s", job_id)
        raise HTTPException(status_code=404, detail="Job not found")
    return view.model_dump(by_alias=True)


async def _run_job(job_id: str) -> None:
    job = await job_store.get(job_id)
    if not job:
        logger.error("Job missing during execution: job_id=%s", job_id)
        return

    try:
        logger.info("Job start: job_id=%s", job_id)
        llm = build_llm()

        await job_store.set_status(job_id, JobStatus.extracting_docs)
        logger.info("Job %s: extracting_docs", job_id)
        passport_path = job.files.get("passport") or _find_first(job.files, "passport")
        g28_path = job.files.get("g28") or _find_first(job.files, "g28")
        if not passport_path or not g28_path:
            raise RuntimeError("Passport and G-28 files are required")

        logger.info(
            "Job %s: OCR/text extraction on %s and %s",
            job_id,
            Path(passport_path).name,
            Path(g28_path).name,
        )
        passport_text, _passport_ocr = await asyncio.to_thread(
            extract_passport_text, passport_path
        )
        g28_text, _g28_ocr = await asyncio.to_thread(
            extract_pdf_text, g28_path, False, "two-column"
        )
        save_text_log(passport_text, "passport_text")
        save_text_log(g28_text, "g28_text")
        logger.info(
            "Job %s: extracted lengths passport=%s g28=%s",
            job_id,
            len(passport_text),
            len(g28_text),
        )

        await job_store.set_status(job_id, JobStatus.filling_form)
        logger.info("Job %s: scan+fill with document context", job_id)
        required_fields, extracted_values, fill_summary = await scan_and_fill_form(
            llm,
            job.form_url,
            passport_text,
            g28_text,
        )
        logger.info(
            "Job %s: scan+fill results fields=%s values=%s summary_len=%s",
            job_id,
            len(required_fields),
            len(extracted_values),
            len(fill_summary),
        )

        result = JobResult(
            required_fields=required_fields,
            extracted_values=extracted_values,
            fill_summary=fill_summary,
        )
        await job_store.set_result(job_id, result)
        logger.info("Job %s: done", job_id)
    except Exception as exc:
        logger.exception("Job %s failed: %s", job_id, exc)
        await job_store.set_error(job_id, str(exc))


def _find_first(files: Dict[str, str], hint: str) -> str:
    hint_lower = hint.lower()
    for key, path in files.items():
        if hint_lower in key.lower() or hint_lower in Path(path).name.lower():
            return path
    return ""
