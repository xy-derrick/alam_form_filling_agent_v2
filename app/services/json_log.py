import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


logger = logging.getLogger(__name__)


def save_json_log(payload: Dict[str, Any], prefix: str) -> None:
    log_dir = Path("LOG")
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    filename = f"{prefix}_{timestamp}_{uuid.uuid4().hex}.json"
    path = log_dir / filename
    try:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        logger.info("Saved JSON log: %s", path)
    except Exception as exc:  # pragma: no cover - log only
        logger.error("Failed to save JSON log: %s", exc)


def save_text_log(text: str, prefix: str) -> None:
    log_dir = Path("LOG")
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    filename = f"{prefix}_{timestamp}_{uuid.uuid4().hex}.txt"
    path = log_dir / filename
    try:
        path.write_text(text, encoding="utf-8")
        logger.info("Saved text log: %s", path)
    except Exception as exc:  # pragma: no cover - log only
        logger.error("Failed to save text log: %s", exc)
