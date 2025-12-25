import asyncio
import ast
import json
import logging
import re
from typing import List, Tuple

from app.config import settings
from app.models.schemas import FieldRequirement, FieldValue
from app.services.json_log import save_json_log, save_text_log

try:
    from browser_use import Agent, Browser
except ImportError:  # pragma: no cover
    Agent = None
    Browser = None


logger = logging.getLogger(__name__)


async def scan_form_fields(llm, form_url: str) -> List[FieldRequirement]:
    logger.info("Scanning form fields: %s", form_url)
    task = f"""
Open this form: {form_url}
Identify all user-fillable fields in the main form and list what information is required.
Return JSON only with this shape:
{{
  "fields": [
    {{
      "name": "short machine-friendly field name",
      "label": "visible label or placeholder",
      "type": "text|date|select|checkbox|radio|email|tel|address|number|file",
      "required": true,
      "notes": "any helper text or constraints"
    }}
  ]
}}
Use double quotes for all JSON keys and string values. Do not include trailing text.
""".strip()

    output, browser = await _run_agent(task, llm, keep_open=False)
    save_text_log(output, "agent_form_fields_raw")
    data = _parse_json(output, prefix="agent_form_fields")
    fields = []
    for item in data.get("fields", []):
        fields.append(
            FieldRequirement(
                name=str(item.get("name", "")),
                label=str(item.get("label", "")),
                type=str(item.get("type", "text")),
                required=bool(item.get("required", False)),
                notes=item.get("notes"),
            )
        )
    _close_browser(browser)
    logger.info("Form scan complete: %s fields", len(fields))
    return fields


async def fill_form(llm, form_url: str, values: List[FieldValue]) -> str:
    logger.info("Filling form: %s with %s values", form_url, len(values))
    values_payload = [
        {"name": item.name, "value": item.value, "notes": item.notes or ""}
        for item in values
    ]
    task = f"""
Open this form: {form_url}
Fill the form using the provided field values. Do not submit the form.
Stop after filling and leave the form ready for human review.

Field values (JSON):
{values_payload}

Return a short summary of what was filled and what was missing.
""".strip()

    output, _browser = await _run_agent(task, llm, keep_open=True)
    summary = str(output).strip()
    logger.info("Fill run complete; summary length=%s", len(summary))
    return summary


async def scan_and_fill_form(
    llm,
    form_url: str,
    passport_text: str,
    g28_text: str,
) -> tuple[List[FieldRequirement], List[FieldValue], str]:
    logger.info("Scanning and filling form with document context: %s", form_url)
    task = f"""
Open this form: {form_url}
You are given Passport text and G-28 text below.
Identify all user-fillable fields, fill them immediately using the document data,
and do not submit the form. Leave the browser ready for human review.

Passport text:
{passport_text}

G-28 text:
{g28_text}

Return JSON only with this shape:
{{
  "fields": [
    {{
      "name": "short machine-friendly field name",
      "label": "visible label or placeholder",
      "type": "text|date|select|checkbox|radio|email|tel|address|number|file",
      "required": true,
      "notes": "any helper text or constraints"
    }}
  ],
  "values": [
    {{
      "name": "field name from fields",
      "value": "value used to fill the form (empty string if missing)",
      "source": "passport|g28|both|unknown",
      "notes": "short reason or location"
    }}
  ],
  "summary": "short summary of filled vs missing fields"
}}
Use double quotes for all JSON keys and string values. Do not include trailing text.
""".strip()

    output, _browser = await _run_agent(task, llm, keep_open=True)
    save_text_log(output, "agent_scan_fill_raw")
    data = _parse_json(output, prefix="agent_scan_fill")
    fields = []
    for item in data.get("fields", []):
        fields.append(
            FieldRequirement(
                name=str(item.get("name", "")),
                label=str(item.get("label", "")),
                type=str(item.get("type", "text")),
                required=bool(item.get("required", False)),
                notes=item.get("notes"),
            )
        )

    values = []
    for item in data.get("values", []):
        values.append(
            FieldValue(
                name=str(item.get("name", "")),
                value=str(item.get("value", "")),
                source=item.get("source"),
                notes=item.get("notes"),
            )
        )

    summary = str(data.get("summary", "")).strip()
    logger.info("Scan+fill complete: fields=%s values=%s", len(fields), len(values))
    return fields, values, summary


async def _run_agent(task: str, llm, keep_open: bool) -> Tuple[str, object]:
    if Agent is None:
        raise RuntimeError("browser_use is not installed")

    browser = Browser(headless=False,keep_alive=True)

    logger.info("Agent run start (keep_open=%s)", keep_open)
    agent = Agent(task=task, llm=llm, browser=browser)
    result = agent.run()
    if asyncio.iscoroutine(result):
        result = await result
    logger.info("Agent run finished")
    return str(result), browser


def _close_browser(browser: object) -> None:
    if browser is None:
        return
    close_fn = getattr(browser, "close", None)
    if callable(close_fn):
        logger.info("Closing browser session")
        close_fn()


def _parse_json(text: str, prefix: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json", "", 1).strip()
    if text.startswith("{") and text.endswith("}"):
        parsed = json.loads(text)
        save_json_log(parsed, prefix)
        return parsed
    match = re.search(r"\{", text)
    if not match:
        logger.error("Agent response did not contain JSON")
        raise ValueError("No JSON object found in agent response")
    decoder = json.JSONDecoder()
    candidate = _extract_balanced_json(text[match.start() :])
    try:
        parsed, _ = decoder.raw_decode(candidate)
        save_json_log(parsed, prefix)
        return parsed
    except json.JSONDecodeError as exc:
        logger.error("Agent JSON parse failed: %s", exc)

    trimmed = candidate

    try:
        parsed = ast.literal_eval(trimmed)
    except Exception:
        normalized = re.sub(r":\s*true\b", ": True", trimmed)
        normalized = re.sub(r":\s*false\b", ": False", normalized)
        normalized = re.sub(r":\s*null\b", ": None", normalized)
        parsed = ast.literal_eval(normalized)

    if isinstance(parsed, dict):
        save_json_log(parsed, prefix)
        return parsed
    if isinstance(parsed, list):
        wrapped = {"fields": parsed}
        save_json_log(wrapped, prefix)
        return wrapped
    raise ValueError("Parsed response is not a JSON object")


def _extract_balanced_json(text: str) -> str:
    depth = 0
    start = None
    for index, char in enumerate(text):
        if char == "{":
            if start is None:
                start = index
            depth += 1
        elif char == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    return text[start : index + 1]
    return text
