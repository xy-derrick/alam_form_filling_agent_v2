import logging
from typing import List

from app.models.schemas import FieldRequirement, FieldValue
from app.services.llm import invoke_json

logger = logging.getLogger(__name__)


async def map_fields_from_docs(
    llm,
    required_fields: List[FieldRequirement],
    passport_text: str,
    g28_text: str,
) -> List[FieldValue]:
    logger.info(
        "Mapping %s fields with passport_len=%s g28_len=%s",
        len(required_fields),
        len(passport_text),
        len(g28_text),
    )
    fields_payload = [
        {
            "name": field.name,
            "label": field.label,
            "type": field.field_type,
            "required": field.required,
            "notes": field.notes or "",
        }
        for field in required_fields
    ]

    prompt = _build_prompt(fields_payload, passport_text, g28_text)
    result = await invoke_json(llm, prompt)
    values = result.get("values", [])
    logger.info("LLM returned %s mapped values", len(values))
    mapped = []
    for item in values:
        mapped.append(
            FieldValue(
                name=str(item.get("name", "")),
                value=str(item.get("value", "")),
                source=item.get("source"),
                confidence=item.get("confidence"),
                notes=item.get("notes"),
            )
        )
    return mapped


def _build_prompt(fields_payload: List[dict], passport_text: str, g28_text: str) -> str:
    return f"""
You are extracting values for an online form.

Required fields (JSON):
{fields_payload}

Passport text:
{passport_text}

G-28 text:
{g28_text}

Return JSON with this shape:
{{
  "values": [
    {{
      "name": "field name from required fields",
      "value": "extracted value or empty string if missing",
      "source": "passport|g28|both|unknown",
      "confidence": 0.0,
      "notes": "short reason or location"
    }}
  ]
}}

Only return valid JSON. Do not include extra keys.
""".strip()
