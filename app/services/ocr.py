import logging
from io import BytesIO
from pathlib import Path
from typing import Iterable, Tuple

import fitz
import pytesseract
from PIL import Image

from app.config import settings


from passporteye import read_mrz

logger = logging.getLogger(__name__)


def extract_pdf_text(
    pdf_path: str,
    include_mrz: bool = False,
    column_mode: str = "single",
) -> Tuple[str, bool]:
    path = Path(pdf_path)
    if not path.exists():
        logger.warning("PDF not found: %s", pdf_path)
        return "", False

    base_text, total_fields, filled_fields = _extract_text_with_fields(
        path, use_ocr=False, column_mode=column_mode
    )
    if total_fields:
        logger.info(
            "PDF form fields found: %s total, %s with values (%s)",
            total_fields,
            filled_fields,
            path.name,
        )

    if len(base_text.strip()) >= settings.ocr_min_text_length:
        final_text = base_text
        used_ocr = False
    else:
        logger.info("PDF text too short; running OCR: %s", path.name)
        final_text, _, _ = _extract_text_with_fields(
            path, use_ocr=True, column_mode=column_mode
        )
        used_ocr = True

    if include_mrz:
        final_text = _append_mrz_sections(path, final_text)

    return final_text, used_ocr


def extract_passport_text(path: str) -> Tuple[str, bool]:
    file_path = Path(path)
    if not file_path.exists():
        logger.warning("Passport file not found: %s", path)
        return "", False

    if file_path.suffix.lower() == ".pdf":
        text, used_ocr = extract_pdf_text(str(file_path), include_mrz=False)
        mrz_text, mrz_parsed = _extract_mrz_from_pdf_images(file_path)
        if mrz_text:
            text = _append_section(text, "MRZ", mrz_text)
        if mrz_parsed:
            text = _append_section(text, "MRZ PARSED", mrz_parsed)
        return text, used_ocr

    text = _extract_image_text(file_path)
    mrz_text, mrz_parsed = _extract_mrz_with_passporteye(file_path)

    if mrz_text:
        text = _append_section(text, "MRZ", mrz_text)
    if mrz_parsed:
        text = _append_section(text, "MRZ PARSED", mrz_parsed)
    return text, True


def _extract_text_with_fields(
    path: Path, use_ocr: bool, column_mode: str
) -> Tuple[str, int, int]:
    doc = fitz.open(str(path))
    parts = []
    total_fields = 0
    filled_fields = 0
    for index, page in enumerate(doc, start=1):
        logger.info(
            "Reading page %s/%s for %s (use_ocr=%s)",
            index,
            doc.page_count,
            path.name,
            use_ocr,
        )
        page_text, page_total, page_filled = _merge_page_text_with_fields(
            page, use_ocr, column_mode
        )
        total_fields += page_total
        filled_fields += page_filled
        parts.append(page_text)
    return "\n".join(parts), total_fields, filled_fields


def _merge_page_text_with_fields(
    page: fitz.Page, use_ocr: bool, column_mode: str
) -> Tuple[str, int, int]:
    text_lines = (
        _extract_page_text_lines(page)
        if not use_ocr
        else _extract_page_ocr_lines(page)
    )
    field_lines, total, filled = _extract_page_field_lines(page)
    combined = text_lines + field_lines
    ordered = _arrange_lines(combined, page, column_mode)
    merged_text = "\n".join([line for _y, _x, line in ordered if line])
    return merged_text, total, filled


def _extract_page_text_lines(page: fitz.Page) -> list[tuple[float, float, str]]:
    content = page.get_text("dict")
    lines = []
    for block in content.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            line_text = "".join(span.get("text", "") for span in spans).strip()
            if not line_text:
                continue
            bbox = line.get("bbox") or [0, 0, 0, 0]
            lines.append((float(bbox[1]), float(bbox[0]), line_text))
    return lines


def _extract_page_ocr_lines(page: fitz.Page) -> list[tuple[float, float, str]]:
    pix = page.get_pixmap(dpi=200)
    mode = "RGB" if pix.alpha == 0 else "RGBA"
    image = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
    if mode == "RGBA":
        image = image.convert("RGB")
    text = pytesseract.image_to_string(image)
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not raw_lines:
        return []
    page_height = float(page.rect.height or 1)
    step = page_height / (len(raw_lines) + 1)
    return [(step * (index + 1), 0.0, line) for index, line in enumerate(raw_lines)]


def _extract_page_field_lines(
    page: fitz.Page,
) -> Tuple[list[tuple[float, float, str]], int, int]:
    widgets = []
    if hasattr(page, "widgets"):
        widgets = list(page.widgets() or [])

    if not widgets:
        return [], 0, 0

    lines = []
    total = 0
    filled = 0
    for widget in widgets:
        total += 1
        value = getattr(widget, "field_value", None)
        value_text = _normalize_field_value(value)
        if not value_text:
            continue
        filled += 1
        name = str(getattr(widget, "field_name", "") or "")
        label = str(getattr(widget, "field_label", "") or "")
        display = name or label or "field"
        if label and name and label != name:
            display = f"{name} ({label})"
        rect = getattr(widget, "rect", page.rect)
        lines.append((float(rect.y0), float(rect.x0), f"{display}: {value_text}"))

    return lines, total, filled


def _arrange_lines(
    lines: Iterable[tuple[float, float, str]],
    page: fitz.Page,
    column_mode: str,
) -> list[tuple[float, float, str]]:
    if column_mode != "two-column":
        return sorted(lines, key=lambda item: (item[0], item[1]))

    mid = float(page.rect.x0 + (page.rect.width / 2))
    left = [item for item in lines if item[1] <= mid]
    right = [item for item in lines if item[1] > mid]
    left_sorted = sorted(left, key=lambda item: (item[0], item[1]))
    right_sorted = sorted(right, key=lambda item: (item[0], item[1]))
    return left_sorted + right_sorted


def _extract_image_text(path: Path) -> str:
    try:
        image = Image.open(str(path))
    except Exception as exc:
        logger.warning("Failed to open image for OCR: %s (%s)", path.name, exc)
        return ""

    if image.mode != "RGB":
        image = image.convert("RGB")
    return pytesseract.image_to_string(image)


def _append_mrz_sections(path: Path, text: str) -> str:
    mrz_text, mrz_parsed = _extract_mrz_with_passporteye(path)
    if mrz_text:
        text = _append_section(text, "MRZ", mrz_text)
    if mrz_parsed:
        text = _append_section(text, "MRZ PARSED", mrz_parsed)
    if not mrz_text:
        logger.info("MRZ not detected: %s", path.name)
    return text


def _extract_text_ocr(path: Path) -> str:
    doc = fitz.open(str(path))
    texts = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        mode = "RGB" if pix.alpha == 0 else "RGBA"
        image = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
        if mode == "RGBA":
            image = image.convert("RGB")
        texts.append(pytesseract.image_to_string(image))
    return "\n".join(texts)


def _extract_mrz_with_passporteye(path: Path) -> Tuple[str, str]:
    if read_mrz is None:
        logger.warning("PassportEye not installed; skipping MRZ detection.")
        return "", ""

    try:
        if path.suffix.lower() == ".pdf":
            return _extract_mrz_from_pdf_images(path)
        else:
            with path.open("rb") as handle:
                mrz = read_mrz(handle)
            mrz_text = _mrz_to_string(mrz)
            mrz_parsed = _mrz_to_parsed_string(mrz)
            if mrz_text:
                logger.info("PassportEye MRZ detected (%s)", path.name)
            return mrz_text, mrz_parsed
    except Exception as exc:
        logger.warning("PassportEye MRZ detection failed: %s (%s)", path.name, exc)
        return "", ""

    return "", ""


def _extract_mrz_from_pdf_images(path: Path) -> Tuple[str, str]:
    if read_mrz is None:
        logger.warning("PassportEye not installed; skipping MRZ detection.")
        return "", ""
    try:
        doc = fitz.open(str(path))
        for index in range(doc.page_count - 1, -1, -1):
            pix = doc[index].get_pixmap(dpi=300)
            image_bytes = pix.tobytes("png")
            mrz = read_mrz(BytesIO(image_bytes))
            mrz_text = _mrz_to_string(mrz)
            if mrz_text:
                mrz_parsed = _mrz_to_parsed_string(mrz)
                logger.info(
                    "PassportEye MRZ detected on page %s (%s)",
                    index + 1,
                    path.name,
                )
                return mrz_text, mrz_parsed
    except Exception as exc:
        logger.warning("PassportEye MRZ detection failed: %s (%s)", path.name, exc)
        return "", ""
    return "", ""


def _mrz_to_string(mrz: object) -> str:
    if mrz is None:
        return ""
    aux = getattr(mrz, "aux", {}) or {}
    raw_text = aux.get("raw_text") or aux.get("text")
    if raw_text:
        return str(raw_text).strip()
    return str(mrz).strip()


def _mrz_to_parsed_string(mrz: object) -> str:
    if mrz is None:
        return ""
    to_dict = getattr(mrz, "to_dict", None)
    if not callable(to_dict):
        return ""
    try:
        parsed = to_dict()
    except Exception:
        return ""
    lines = []
    for key, value in parsed.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines).strip()


def _normalize_field_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore").strip()
    if isinstance(value, (list, tuple)):
        parts = [_normalize_field_value(item) for item in value]
        return ", ".join([part for part in parts if part])
    text = str(value).strip()
    if text.startswith("/"):
        text = text[1:]
    return text


def _append_section(text: str, title: str, section_text: str) -> str:
    if not section_text:
        return text
    header = f"[{title}]"
    if not text.strip():
        return f"{header}\n{section_text}"
    return f"{text}\n\n{header}\n{section_text}"
