import logging
import shutil
import uuid
from pathlib import Path
from typing import Dict, Tuple

from fastapi import UploadFile

from app.config import settings

logger = logging.getLogger(__name__)


def ensure_upload_root() -> Path:
    upload_root = Path(settings.upload_dir)
    upload_root.mkdir(parents=True, exist_ok=True)
    return upload_root


def save_uploads(passport: UploadFile, g28: UploadFile) -> Tuple[str, Dict[str, str]]:
    upload_root = ensure_upload_root()
    upload_id = str(uuid.uuid4())
    upload_dir = upload_root / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Saving uploads to %s", upload_dir)
    saved = {}
    for key, upload in {"passport": passport, "g28": g28}.items():
        filename = upload.filename or f"{key}.pdf"
        destination = upload_dir / filename
        logger.info("Saving %s to %s", key, destination.name)
        with destination.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)
        saved[key] = str(destination)

    return upload_id, saved


def get_upload_paths(upload_id: str) -> Dict[str, str]:
    upload_root = ensure_upload_root()
    upload_dir = upload_root / upload_id
    if not upload_dir.exists():
        return {}
    files = {}
    for item in upload_dir.iterdir():
        if item.is_file():
            files[item.stem.lower()] = str(item)
    return files
