from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    upload_id: str
    files: Dict[str, str]


class CreateJobRequest(BaseModel):
    upload_id: str
    form_url: str


class JobStatus(str, Enum):
    queued = "queued"
    extracting_docs = "extracting_docs"
    analyzing_form = "analyzing_form"
    mapping_fields = "mapping_fields"
    filling_form = "filling_form"
    done = "done"
    error = "error"


class FieldRequirement(BaseModel):
    name: str
    label: str
    field_type: str = Field(default="text", alias="type")
    required: bool = False
    notes: Optional[str] = None

    model_config = {"populate_by_name": True}


class FieldValue(BaseModel):
    name: str
    value: str
    source: Optional[str] = None
    confidence: Optional[float] = None
    notes: Optional[str] = None


class JobResult(BaseModel):
    required_fields: List[FieldRequirement] = Field(default_factory=list)
    extracted_values: List[FieldValue] = Field(default_factory=list)
    fill_summary: Optional[str] = None


class JobView(BaseModel):
    job_id: str
    status: JobStatus
    error: Optional[str] = None
    result: Optional[JobResult] = None
