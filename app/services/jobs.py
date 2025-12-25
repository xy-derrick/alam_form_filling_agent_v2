import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

from app.models.schemas import JobResult, JobStatus, JobView

logger = logging.getLogger(__name__)


@dataclass
class JobState:
    job_id: str
    upload_id: str
    form_url: str
    files: Dict[str, str] = field(default_factory=dict)
    status: JobStatus = JobStatus.queued
    error: Optional[str] = None
    result: JobResult = field(default_factory=JobResult)


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, JobState] = {}
        self._lock = asyncio.Lock()

    async def create(self, upload_id: str, form_url: str, files: Dict[str, str]) -> JobState:
        async with self._lock:
            job_id = str(uuid.uuid4())
            state = JobState(job_id=job_id, upload_id=upload_id, form_url=form_url, files=files)
            self._jobs[job_id] = state
            logger.info("Job created: job_id=%s upload_id=%s", job_id, upload_id)
            return state

    async def get(self, job_id: str) -> Optional[JobState]:
        async with self._lock:
            return self._jobs.get(job_id)

    async def set_status(self, job_id: str, status: JobStatus) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = status
                logger.info("Job status update: job_id=%s status=%s", job_id, status)

    async def set_error(self, job_id: str, error: str) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = JobStatus.error
                job.error = error
                logger.error("Job error: job_id=%s error=%s", job_id, error)

    async def set_result(self, job_id: str, result: JobResult) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.result = result
                job.status = JobStatus.done
                logger.info("Job result stored: job_id=%s", job_id)

    async def view(self, job_id: str) -> Optional[JobView]:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return JobView(
                job_id=job.job_id,
                status=job.status,
                error=job.error,
                result=job.result,
            )
