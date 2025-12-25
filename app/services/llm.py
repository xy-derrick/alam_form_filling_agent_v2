import json
import logging
import re
from typing import Any, Dict

from browser_use.llm import BaseChatModel, ChatBrowserUse, ChatGoogle, UserMessage

from app.config import settings
from app.services.json_log import save_json_log

logger = logging.getLogger(__name__)


def build_llm() -> BaseChatModel:
    provider = settings.llm_provider.strip().lower()
    if provider in {"browser-use", "browser_use", "browseruse"}:
        logger.info("Initializing Browser Use LLM: %s", settings.browser_use_model)
        return ChatBrowserUse(model=settings.browser_use_model, api_key=settings.browser_use_api_key)

    logger.info("Initializing Gemini model: %s", settings.gemini_model)
    return ChatGoogle(
        model=settings.gemini_model,
        api_key=settings.google_api_key,
        temperature=0,
    )


async def invoke_json(llm: BaseChatModel, prompt: str) -> Dict[str, Any]:
    logger.info("Invoking LLM with prompt length=%s", len(prompt))
    response = await llm.ainvoke([UserMessage(content=prompt)])
    text = getattr(response, "completion", "") or str(response)
    logger.info("LLM response length=%s", len(text))
    parsed = _parse_json(text)
    save_json_log(parsed, "llm_mapping")
    return parsed


def _parse_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        logger.error("LLM response did not contain JSON")
        raise ValueError("No JSON object found in LLM response")
    return json.loads(match.group(0))
