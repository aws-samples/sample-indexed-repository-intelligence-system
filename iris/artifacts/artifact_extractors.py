# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Artifact extractors for supported file formats.

Each extractor takes a file path and returns extracted text content.
Extraction patterns are inspired by the reference engagement_report project
but are self-contained with no runtime dependency on it.
"""

import boto3
from botocore.config import Config
import logging
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
from docx import Document
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from openpyxl import load_workbook
from tqdm import tqdm

from . import DiscoveredArtifact, ExtractionResult, EXTENSION_TO_EXTRACTOR
from ..utils import load_default_config

logger = logging.getLogger(__name__)

# Thread-safe counter for OCR calls within a single indexing run.
# Reset at the start of each extract_artifacts_parallel() invocation.
_ocr_page_count = 0
_ocr_page_lock = threading.Lock()
_ocr_max_pages = 0  # 0 = unlimited

# Valid OCR provider values
_VALID_OCR_PROVIDERS = {"llm", "textract"}


# ---------------------------------------------------------------------------
# Individual extractors
# ---------------------------------------------------------------------------


def extract_from_pptx(
    path: Path,
    ocr_enabled: bool = False,
    ocr_model_config: dict | None = None,
) -> str:
    """Extract slide text, speaker notes, and image descriptions from a .pptx file.

    Uses python-pptx to iterate slides, extracting shape text and
    notes_text_frame content. When *ocr_enabled* is ``True``, embedded
    images (pictures) are sent to a multimodal LLM for analysis —
    useful for architecture diagrams, tables, and screenshots.
    """
    prs = Presentation(str(path))
    content = [f"# Source: {path.name}\n"]

    for i, slide in enumerate(prs.slides, 1):
        content.append(f"\n## Slide {i}\n")
        image_idx = 0
        for shape in slide.shapes:
            if shape.has_table:
                table = shape.table
                rows = []
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    rows.append("| " + " | ".join(cells) + " |")
                if rows:
                    header_sep = "| " + " | ".join(["---"] * len(table.columns)) + " |"
                    rows.insert(1, header_sep)
                content.append("\n".join(rows))
            elif hasattr(shape, "text") and shape.text.strip():
                content.append(shape.text.strip())
            # Analyze embedded images when OCR is enabled
            if (
                ocr_enabled
                and shape.shape_type == MSO_SHAPE_TYPE.PICTURE
                and hasattr(shape, "image")
            ):
                image_idx += 1
                try:
                    img_blob = shape.image.blob
                    img_ct = shape.image.content_type  # e.g. "image/png"
                    fmt = img_ct.split("/")[-1] if "/" in img_ct else "png"
                    # Normalize format for Bedrock API
                    if fmt == "jpg":
                        fmt = "jpeg"
                    if fmt not in ("png", "jpeg", "gif", "webp"):
                        fmt = "png"
                    label = f"Slide {i}, Image {image_idx}"
                    desc = _analyze_image_with_llm(
                        img_blob,
                        fmt,
                        path.name,
                        label,
                        ocr_model_config,
                    )
                    if desc:
                        content.append(f"\n**[{label}]**\n{desc}")
                except Exception as exc:
                    logger.warning(
                        "Failed to extract image from %s slide %d: %s",
                        path.name,
                        i,
                        exc,
                    )
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
            content.append(
                f"\n**Notes:** {slide.notes_slide.notes_text_frame.text.strip()}"
            )

    return "\n".join(content)


def extract_from_docx(
    path: Path,
    ocr_enabled: bool = False,
    ocr_model_config: dict | None = None,
) -> str:
    """Extract paragraph text and image descriptions from a .docx file.

    Uses python-docx to iterate paragraphs and concatenate non-empty text.
    When *ocr_enabled* is ``True``, inline images are extracted and sent
    to a multimodal LLM for analysis — useful for architecture diagrams,
    flowcharts, and tables embedded as images.
    """
    doc = Document(str(path))
    content = [f"# Source: {path.name}\n"]

    # Collect all images from the document's image relationships
    image_parts = {}
    if ocr_enabled:
        for rel in doc.part.rels.values():
            if "image" in rel.reltype:
                image_parts[rel.rId] = rel.target_part

    # Helper: extract images (inline + floating) from an XML element
    _BLIP_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
    _EMBED_NS = (
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
    )

    def _extract_images_from_element(element, image_idx):
        """Find all blip references (inline and anchored images) in an XML element."""
        if not ocr_enabled or not image_parts:
            return image_idx
        for blip in element.findall(f".//{_BLIP_NS}"):
            embed = blip.get(_EMBED_NS)
            if embed and embed in image_parts:
                image_idx += 1
                try:
                    img_part = image_parts[embed]
                    img_bytes = img_part.blob
                    ct = img_part.content_type
                    fmt = ct.split("/")[-1] if "/" in ct else "png"
                    if fmt == "jpg":
                        fmt = "jpeg"
                    if fmt not in ("png", "jpeg", "gif", "webp"):
                        fmt = "png"
                    label = f"Image {image_idx}"
                    desc = _analyze_image_with_llm(
                        img_bytes,
                        fmt,
                        path.name,
                        label,
                        ocr_model_config,
                    )
                    if desc:
                        content.append(f"\n**[{label}]**\n{desc}")
                except Exception as exc:
                    logger.warning(
                        "Failed to extract image %d from %s: %s",
                        image_idx,
                        path.name,
                        exc,
                    )
        return image_idx

    # Build lookup maps so we can iterate body elements in document order
    para_map = {p._element: p for p in doc.paragraphs}
    table_map = {t._element: t for t in doc.tables}

    image_idx = 0
    for child in doc.element.body:
        # --- Paragraph ---
        if child in para_map:
            para = para_map[child]
            if para.text.strip():
                content.append(para.text.strip())
            # Extract inline + floating images from this paragraph
            image_idx = _extract_images_from_element(child, image_idx)

        # --- Table ---
        elif child in table_map:
            table = table_map[child]
            rows = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                rows.append("| " + " | ".join(cells) + " |")
            if rows:
                header_sep = "| " + " | ".join(["---"] * len(table.columns)) + " |"
                rows.insert(1, header_sep)
                content.append("\n" + "\n".join(rows))
            # Extract images embedded inside table cells
            image_idx = _extract_images_from_element(child, image_idx)

    return "\n".join(content)


def extract_from_xlsx(path: Path) -> str:
    """Extract cell data from a .xlsx file.

    Uses openpyxl to iterate over all sheets and rows, concatenating
    non-empty cell values. Prefixes output with source filename.
    """
    wb = load_workbook(str(path), read_only=True, data_only=True)
    content = [f"# Source: {path.name}\n"]

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        content.append(f"\n## Sheet: {sheet_name}\n")
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                content.append(" | ".join(cells))

    wb.close()
    return "\n".join(content)


def parse_docs(path: Path) -> str:
    """Parse .md and .txt files.

    Reads the file content and prefixes it with the source filename.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    return f"# Source: {path.name}\n\n{text}"


def _check_ocr_limit(path: Path, page_number: int) -> bool:
    """Check and increment the OCR page counter (thread-safe).

    Returns ``True`` if the page can be processed, ``False`` if the limit
    has been reached.
    """
    global _ocr_page_count
    with _ocr_page_lock:
        if _ocr_max_pages > 0 and _ocr_page_count >= _ocr_max_pages:
            logger.warning(
                "OCR page limit reached (%d). Skipping OCR for %s page %d.",
                _ocr_max_pages,
                path.name,
                page_number,
            )
            return False
        _ocr_page_count += 1
        return True


def _render_page_to_png(page) -> bytes:
    """Render a pdfplumber page to PNG bytes at 300 DPI."""
    import io

    pil_image = page.to_image(resolution=300).original
    img_buffer = io.BytesIO()
    pil_image.save(img_buffer, format="PNG")
    return img_buffer.getvalue()


def _analyze_image_with_llm(
    img_bytes: bytes,
    image_format: str,
    source_name: str,
    context_label: str,
    model_config: dict | None = None,
) -> Optional[str]:
    """Analyze an embedded image using a multimodal LLM (Claude via Bedrock).

    Sends the image to Bedrock's ``converse`` API with a prompt that asks
    the LLM to describe diagrams, extract text, and interpret visual content.

    Respects the global ``_ocr_max_pages`` limit (shared with PDF OCR).
    Returns *None* on any failure so the caller can skip gracefully.

    Parameters
    ----------
    img_bytes : bytes
        Raw image bytes (PNG, JPEG, etc.).
    image_format : str
        Image format for the Bedrock API (``"png"``, ``"jpeg"``, ``"gif"``).
    source_name : str
        Filename of the source document (for logging).
    context_label : str
        Human-readable label like ``"Slide 3, Image 2"`` (for logging and output).
    model_config : dict | None
        Bedrock model config dict with ``model_id`` and ``region``.
    """
    # Use a dummy page_number=0 for the limit check — the counter is global
    if not _check_ocr_limit(Path(source_name), 0):
        return None

    try:
        if model_config is None:
            cfg = load_default_config()
            models = cfg["model_configuration"]["file_summarizer"]["models"]
            model_config = models[0]

        boto3_config = Config(
            region_name=model_config["region"],
            read_timeout=120,
            retries={"mode": "standard", "max_attempts": 3},
        )
        bedrock_client = boto3.client("bedrock-runtime", config=boto3_config)

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "image": {
                            "format": image_format,
                            "source": {"bytes": img_bytes},
                        }
                    },
                    {
                        "text": (
                            f"This image is from '{source_name}' ({context_label}). "
                            "Analyze this image thoroughly:\n"
                            "- If it contains a diagram (architecture, flow, sequence, etc.), "
                            "describe the components, connections, and data flow.\n"
                            "- If it contains a table, reproduce the table structure and data.\n"
                            "- If it contains text, extract all visible text.\n"
                            "- If it contains a screenshot or UI, describe what is shown.\n"
                            "Output ONLY the analysis, nothing else."
                        ),
                    },
                ],
            }
        ]

        response = bedrock_client.converse(
            modelId=model_config["model_id"],
            messages=messages,
            system=[
                {
                    "text": (
                        "You are a precise visual analyst specializing in technical documents. "
                        "Describe diagrams, extract text, and interpret visual content accurately."
                    )
                }
            ],
            inferenceConfig={"temperature": 0, "maxTokens": 4096},
        )

        text = response["output"]["message"]["content"][0]["text"]
        if text and text.strip():
            return text.strip()
        return None

    except Exception as exc:
        logger.warning(
            "LLM image analysis failed for %s (%s): %s",
            source_name,
            context_label,
            exc,
        )
        return None


def _ocr_pdf_page_with_textract(path: Path, page_number: int, page) -> Optional[str]:
    """Use Amazon Textract to OCR a single PDF page rendered as an image.

    Renders the page to a PNG image via pdfplumber, sends it to Textract
    ``DetectDocumentText``, and returns the extracted text. Returns *None*
    on any failure so the caller can fall back gracefully.
    """
    if not _check_ocr_limit(path, page_number):
        return None

    try:
        import boto3

        img_bytes = _render_page_to_png(page)

        client = boto3.client("textract")
        response = client.detect_document_text(Document={"Bytes": img_bytes})

        lines = []
        for block in response.get("Blocks", []):
            if block["BlockType"] == "LINE":
                lines.append(block["Text"])

        if lines:
            return "\n".join(lines)
        return None

    except ImportError as exc:
        logger.warning(
            "OCR dependencies missing for %s page %d: %s",
            path.name,
            page_number,
            exc,
        )
        return None
    except Exception as exc:
        logger.warning(
            "Textract OCR failed for %s page %d: %s",
            path.name,
            page_number,
            exc,
        )
        return None


def _ocr_pdf_page_with_llm(
    path: Path, page_number: int, page, model_config: dict | None = None
) -> Optional[str]:
    """Use a multimodal LLM (Claude via Bedrock) to extract text from an image-only PDF page.

    Renders the page to a PNG image via pdfplumber, sends it to Bedrock's
    ``converse`` API with a text extraction prompt, and returns the extracted
    text. Returns *None* on any failure so the caller can fall back gracefully.

    Respects the global ``_ocr_max_pages`` limit — returns *None* without
    calling the LLM if the limit has been reached.
    """
    if not _check_ocr_limit(path, page_number):
        return None

    try:
        img_bytes = _render_page_to_png(page)

        # Resolve model config
        if model_config is None:
            from ..utils import load_default_config

            config = load_default_config()
            models = config["model_configuration"]["file_summarizer"]["models"]
            model_config = models[0]

        model_id = model_config["model_id"]
        region = model_config["region"]
        boto3_config = Config(
            region_name=region,
            read_timeout=120,
            retries={"mode": "standard", "max_attempts": 3},
        )
        bedrock_client = boto3.client("bedrock-runtime", config=boto3_config)

        # Build converse message with image
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "image": {
                            "format": "png",
                            "source": {"bytes": img_bytes},
                        }
                    },
                    {
                        "text": (
                            "Extract ALL text content from this PDF page image. "
                            "Preserve the original structure, headings, bullet points, "
                            "and table layouts as closely as possible. "
                            "Output ONLY the extracted text, nothing else."
                        ),
                    },
                ],
            }
        ]

        response = bedrock_client.converse(
            modelId=model_id,
            messages=messages,
            system=[
                {
                    "text": "You are a precise OCR assistant. Extract text exactly as it appears in the image."
                }
            ],
            inferenceConfig={"temperature": 0, "maxTokens": 4096},
        )

        text = response["output"]["message"]["content"][0]["text"]
        if text and text.strip():
            return text.strip()
        return None

    except ImportError as exc:
        logger.warning(
            "OCR dependencies missing for %s page %d: %s",
            path.name,
            page_number,
            exc,
        )
        return None
    except Exception as exc:
        logger.warning(
            "LLM OCR failed for %s page %d: %s",
            path.name,
            page_number,
            exc,
        )
        return None


def _describe_pdf_page_images(
    path: Path, page_number: int, page, model_config: dict | None = None
) -> Optional[str]:
    """Describe images/diagrams on a PDF page that also contains extractable text.

    Renders the page to PNG and asks the LLM to describe only the visual
    elements (diagrams, charts, figures) — the surrounding text is already
    captured by ``extract_text()``.

    Respects the global OCR page budget.  Returns *None* on failure.
    """
    if not _check_ocr_limit(path, page_number):
        return None

    try:
        img_bytes = _render_page_to_png(page)

        # Resolve model config
        if model_config is None:
            from ..utils import load_default_config

            config = load_default_config()
            models = config["model_configuration"]["file_summarizer"]["models"]
            model_config = models[0]

        model_id = model_config["model_id"]
        region = model_config["region"]
        boto3_config = Config(
            region_name=region,
            read_timeout=120,
            retries={"mode": "standard", "max_attempts": 3},
        )
        bedrock_client = boto3.client("bedrock-runtime", config=boto3_config)

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "image": {
                            "format": "png",
                            "source": {"bytes": img_bytes},
                        }
                    },
                    {
                        "text": (
                            "This PDF page contains both text and visual elements. "
                            "The text has already been extracted separately. "
                            "Describe ONLY the visual elements on this page — "
                            "diagrams, charts, figures, flowcharts, or images. "
                            "If a visual contains a table, reproduce the table "
                            "structure and data in markdown format. "
                            "If there are no visual elements, respond with exactly: "
                            "NO_VISUAL_ELEMENTS"
                        ),
                    },
                ],
            }
        ]

        response = bedrock_client.converse(
            modelId=model_id,
            messages=messages,
            system=[
                {
                    "text": (
                        "You are a precise document analysis assistant. "
                        "Focus only on visual elements, not text content."
                    )
                }
            ],
            inferenceConfig={"temperature": 0, "maxTokens": 4096},
        )

        text = response["output"]["message"]["content"][0]["text"]
        if text and text.strip() and "NO_VISUAL_ELEMENTS" not in text:
            return text.strip()
        return None

    except Exception as exc:
        logger.warning(
            "Image description failed for %s page %d: %s",
            path.name,
            page_number,
            exc,
        )
        return None


def extract_from_pdf(
    path: Path,
    ocr_enabled: bool = False,
    ocr_provider: str = "llm",
    ocr_model_config: dict | None = None,
) -> str:
    """Extract text from all pages of a .pdf file using pdfplumber.

    Prefixes output with source filename. When *ocr_enabled* is ``True``,
    image-only pages (no extractable text) are OCR'd using the selected
    *ocr_provider*:

    - ``"llm"`` — sends the page image to a multimodal LLM (Claude via Bedrock)
    - ``"textract"`` — sends the page image to Amazon Textract

    Otherwise, image-only pages are skipped with a warning.
    Logs an error and returns empty content for password-protected files.
    """
    import pdfplumber

    # Suppress noisy pdfminer font warnings (e.g. malformed FontBBox)
    logging.getLogger("pdfminer.pdffont").setLevel(logging.ERROR)

    try:
        pdf = pdfplumber.open(str(path))
    except Exception as exc:
        logger.error("Cannot open PDF %s: %s", path.name, exc)
        return f"# Source: {path.name}\n\n[Error: unable to read PDF — {exc}]"

    content = [f"# Source: {path.name}\n"]

    for i, page in enumerate(pdf.pages, 1):
        text = page.extract_text()
        if text and text.strip():
            content.append(f"\n## Page {i}\n")
            content.append(text.strip())
            # Extract structured tables (pdfplumber can detect table grids)
            tables = page.extract_tables()
            if tables:
                for t_idx, table_data in enumerate(tables, 1):
                    rows = []
                    for row in table_data:
                        cells = [(c or "").strip() for c in row]
                        rows.append("| " + " | ".join(cells) + " |")
                    if rows:
                        header_sep = (
                            "| " + " | ".join(["---"] * len(table_data[0])) + " |"
                        )
                        rows.insert(1, header_sep)
                        content.append("\n" + "\n".join(rows))
            # Check for images on pages that also have text
            if ocr_enabled and hasattr(page, "images") and page.images:
                img_desc = _describe_pdf_page_images(path, i, page, ocr_model_config)
                if img_desc:
                    content.append(f"\n**[Page {i}, Embedded Visual]**\n{img_desc}")
        elif ocr_enabled:
            provider_label = ocr_provider.upper()
            logger.info(
                "PDF %s page %d: no text found, attempting %s OCR...",
                path.name,
                i,
                provider_label,
            )
            if ocr_provider == "textract":
                ocr_text = _ocr_pdf_page_with_textract(path, i, page)
            else:
                ocr_text = _ocr_pdf_page_with_llm(path, i, page, ocr_model_config)
            if ocr_text:
                content.append(f"\n## Page {i} (OCR)\n")
                content.append(ocr_text)
            else:
                logger.warning(
                    "PDF %s page %d: OCR returned no text",
                    path.name,
                    i,
                )
        else:
            logger.warning(
                "PDF %s page %d: no extractable text (image-only?). "
                "Enable artifact_ocr_enabled in config for OCR.",
                path.name,
                i,
            )

    pdf.close()
    return "\n".join(content)


def _get_video_duration_seconds(path: Path) -> Optional[float]:
    """Get video duration in seconds using ffprobe.

    Returns *None* if ffprobe is not available or fails.
    """
    import subprocess

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError) as exc:
        logger.warning("ffprobe failed for %s: %s", path.name, exc)
    return None


def _format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _extract_frame_at(path: Path, timestamp_sec: float) -> Optional[bytes]:
    """Extract a single frame from a video at the given timestamp using ffmpeg.

    Returns PNG bytes or *None* on failure.
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-ss",
                str(timestamp_sec),
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-vcodec",
                "png",
                "-",
            ],
            capture_output=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning(
            "ffmpeg frame extraction failed for %s at %.1fs: %s",
            path.name,
            timestamp_sec,
            exc,
        )
    return None


def _describe_frame_with_llm(
    frame_bytes: bytes,
    video_name: str,
    timestamp_label: str,
    model_config: dict | None = None,
) -> str:
    """Send a video frame image to a multimodal LLM for description.

    Returns the LLM's description text, or a fallback message on failure.
    """
    try:
        if model_config is None:
            cfg = load_default_config()
            models = cfg["model_configuration"]["file_summarizer"]["models"]
            model_config = models[0]

        boto3_config = Config(
            region_name=model_config["region"],
            read_timeout=120,
            retries={"mode": "standard", "max_attempts": 3},
        )
        bedrock_client = boto3.client("bedrock-runtime", config=boto3_config)

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "image": {
                            "format": "png",
                            "source": {"bytes": frame_bytes},
                        }
                    },
                    {
                        "text": (
                            f"This is a frame from the video '{video_name}' at timestamp {timestamp_label}. "
                            "Describe what is shown in this frame in detail — include any visible text, "
                            "slide content, diagrams, UI elements, or people/activities. "
                            "Output ONLY the description, nothing else."
                        ),
                    },
                ],
            }
        ]

        response = bedrock_client.converse(
            modelId=model_config["model_id"],
            messages=messages,
            system=[
                {
                    "text": "You are a precise visual analyst. Describe video frames accurately and concisely."
                }
            ],
            inferenceConfig={"temperature": 0, "maxTokens": 2048},
        )

        return response["output"]["message"]["content"][0]["text"].strip()

    except Exception as exc:
        logger.warning(
            "LLM frame description failed for %s at %s: %s",
            video_name,
            timestamp_label,
            exc,
        )
        return f"[Frame description unavailable: {exc}]"


def _extract_keyframes_with_llm(
    path: Path,
    duration_sec: float,
    model_config: dict | None = None,
) -> list[str]:
    """Extract 3 keyframes (near beginning, middle, near end) and describe each with LLM.

    Returns a list of formatted description strings.
    """
    # Pick timestamps at ~10%, 50%, 90% of duration
    timestamps = [
        duration_sec * 0.10,
        duration_sec * 0.50,
        duration_sec * 0.90,
    ]
    labels = ["near beginning", "middle", "near end"]
    descriptions = []

    for ts, label in zip(timestamps, labels):
        ts_label = _format_timestamp(ts)
        frame_bytes = _extract_frame_at(path, ts)
        if frame_bytes:
            desc = _describe_frame_with_llm(
                frame_bytes, path.name, ts_label, model_config
            )
            descriptions.append(f"### Frame — {label} ({ts_label})\n{desc}")
        else:
            descriptions.append(
                f"### Frame — {label} ({ts_label})\n[Frame extraction failed]"
            )

    return descriptions


def _download_transcript_json(transcript_uri: str, region: str) -> dict:
    """Download AWS Transcribe transcript JSON.

    Uses the ``requests`` library which ships with ``certifi`` for SSL,
    avoiding macOS certificate issues.
    """
    import requests as _req
    from urllib.parse import urlparse

    parsed = urlparse(transcript_uri)
    if parsed.scheme not in ("https",):
        raise ValueError(
            f"Unsupported URI scheme: {parsed.scheme!r} (only https is allowed)"
        )

    resp = _req.get(transcript_uri, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _transcribe_video_with_aws(
    path: Path,
    s3_bucket: str,
    s3_prefix: str = "iris-transcribe-temp/",
    region: str = "us-east-1",
) -> Optional[str]:
    """Upload video to S3, run Amazon Transcribe, return transcript text.

    Cleans up the S3 upload after transcription completes.
    Returns *None* on any failure.
    """
    import time
    import uuid

    try:
        import boto3

        s3_client = boto3.client("s3", region_name=region)
        transcribe_client = boto3.client("transcribe", region_name=region)

        # Upload to S3
        s3_key = f"{s3_prefix}{uuid.uuid4().hex}_{path.name}"
        logger.info("Uploading %s to s3://%s/%s ...", path.name, s3_bucket, s3_key)
        s3_client.upload_file(str(path), s3_bucket, s3_key)

        s3_uri = f"s3://{s3_bucket}/{s3_key}"
        job_name = f"iris-{uuid.uuid4().hex[:12]}"

        # Determine media format
        ext = path.suffix.lower().lstrip(".")
        media_format_map = {"mp4": "mp4", "mov": "mp4", "avi": "mp4", "mkv": "mp4"}
        media_format = media_format_map.get(ext, "mp4")

        # Start transcription job
        logger.info("Starting Transcribe job '%s' for %s ...", job_name, path.name)
        transcribe_client.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": s3_uri},
            MediaFormat=media_format,
            LanguageCode="en-US",
        )

        # Poll for completion
        while True:
            status = transcribe_client.get_transcription_job(
                TranscriptionJobName=job_name
            )
            job_status = status["TranscriptionJob"]["TranscriptionJobStatus"]

            if job_status == "COMPLETED":
                transcript_uri = status["TranscriptionJob"]["Transcript"][
                    "TranscriptFileUri"
                ]
                logger.info("Transcribe job '%s' completed.", job_name)
                break
            elif job_status == "FAILED":
                reason = status["TranscriptionJob"].get("FailureReason", "unknown")
                logger.error("Transcribe job '%s' failed: %s", job_name, reason)
                # Cleanup S3
                _s3_cleanup(s3_client, s3_bucket, s3_key)
                return None
            else:
                time.sleep(15)

        # Download transcript – avoid urllib.request.urlopen which can
        # fail on macOS Python 3.13+ with SSL: CERTIFICATE_VERIFY_FAILED.
        # Try requests/certifi first, fall back to plain urllib.
        transcript_json = _download_transcript_json(transcript_uri, region)

        transcript_text = transcript_json["results"]["transcripts"][0]["transcript"]

        # Cleanup S3
        _s3_cleanup(s3_client, s3_bucket, s3_key)

        # Also try to delete the transcription job (best effort)
        try:
            transcribe_client.delete_transcription_job(TranscriptionJobName=job_name)
        except Exception:
            pass

        return transcript_text if transcript_text.strip() else None

    except Exception as exc:
        logger.error("Video transcription failed for %s: %s", path.name, exc)
        return None


def _s3_cleanup(s3_client, bucket: str, key: str) -> None:
    """Best-effort cleanup of a temporary S3 object."""
    try:
        s3_client.delete_object(Bucket=bucket, Key=key)
        logger.info("Cleaned up s3://%s/%s", bucket, key)
    except Exception as exc:
        logger.warning("Failed to clean up s3://%s/%s: %s", bucket, key, exc)


def extract_from_video(
    path: Path,
    transcription_config: dict | None = None,
    model_config: dict | None = None,
) -> str:
    """Extract content from video files using a combined approach.

    Always collects basic metadata (filename, size, format, duration).

    When *transcription_config* is provided and enabled:
    1. Extracts 3 keyframes (near beginning, middle, near end) and sends
       each to a multimodal LLM for visual description.
    2. Uploads the video to S3 and runs Amazon Transcribe for speech-to-text.
    3. Consolidates metadata + frame descriptions + transcript into one output.

    Falls back gracefully if ffmpeg/ffprobe is unavailable or transcription fails.
    """
    stat = path.stat()
    size_mb = stat.st_size / (1024 * 1024)
    ext = path.suffix.lower()

    content = [f"# Source: {path.name}\n"]
    content.append("## Metadata")
    content.append(f"- Format: {ext.lstrip('.')}")
    content.append(f"- Size: {size_mb:.1f} MB")

    # Get duration
    duration_sec = _get_video_duration_seconds(path)
    if duration_sec:
        content.append(f"- Duration: {_format_timestamp(duration_sec)}")

    # Check if transcription is enabled
    tc = transcription_config or {}
    transcription_enabled = tc.get("artifact_transcription_enabled", False)

    if not transcription_enabled:
        content.append("\n[Video transcription not enabled — metadata only]")
        return "\n".join(content)

    # --- Keyframe analysis (LLM) ---
    if duration_sec and duration_sec > 0:
        content.append("\n## Visual Content (LLM Frame Analysis)\n")
        try:
            frame_descriptions = _extract_keyframes_with_llm(
                path, duration_sec, model_config
            )
            content.extend(frame_descriptions)
        except Exception as exc:
            logger.warning("Keyframe analysis failed for %s: %s", path.name, exc)
            content.append("[Keyframe analysis failed]")
    else:
        content.append("\n## Visual Content\n")
        content.append("[Could not determine video duration — skipping frame analysis]")

    # --- Transcription (Amazon Transcribe) ---
    s3_bucket = tc.get("artifact_transcribe_s3_bucket", "")
    s3_prefix = "iris-transcribe-temp/"

    if s3_bucket:
        # Derive region from the S3 bucket — Transcribe must run in the same region
        try:
            s3_client = boto3.client("s3")
            resp = s3_client.get_bucket_location(Bucket=s3_bucket)
            region = resp["LocationConstraint"] or "us-east-1"  # None means us-east-1
        except Exception as exc:
            logger.warning(
                "Could not determine region for bucket %s: %s, defaulting to us-east-1",
                s3_bucket,
                exc,
            )
            region = "us-east-1"

        content.append("\n## Transcript (Amazon Transcribe)\n")
        logger.info(
            "Starting transcription for %s (this may take several minutes)...",
            path.name,
        )
        transcript = _transcribe_video_with_aws(path, s3_bucket, s3_prefix, region)
        if transcript:
            content.append(transcript)
        else:
            content.append("[Transcription failed or returned empty]")
    else:
        content.append("\n## Transcript\n")
        content.append("[No S3 bucket configured — skipping transcription]")

    return "\n".join(content)


# ---------------------------------------------------------------------------
# Extractor router
# ---------------------------------------------------------------------------

_EXTRACTOR_MAP = {
    "xlsx": extract_from_xlsx,
    "docs": parse_docs,
}


def extract_artifact(
    artifact: DiscoveredArtifact,
    max_file_size: int = 30_000_000,
    video_max_file_size: int = 300_000_000,
    transcription_config: dict | None = None,
    ocr_enabled: bool = False,
    ocr_provider: str = "llm",
    ocr_model_config: dict | None = None,
) -> ExtractionResult:
    """Route an artifact to the correct extractor and return the result.

    Enforces *max_file_size* — files larger than the limit are skipped.
    Catches all exceptions and returns a failed :class:`ExtractionResult`
    rather than propagating.
    """
    path = artifact.absolute_path

    # Determine effective size limit — video files get a higher threshold
    ext = f".{artifact.file_format}"
    extractor_name = EXTENSION_TO_EXTRACTOR.get(ext)
    effective_max = video_max_file_size if extractor_name == "video" else max_file_size

    # Size check
    try:
        file_size = path.stat().st_size
    except OSError as exc:
        logger.error("Cannot stat %s: %s", artifact.file_path, exc)
        return ExtractionResult(
            file_path=artifact.file_path,
            content="",
            file_format=artifact.file_format,
            project_phase=artifact.project_phase,
            source_material_type=artifact.source_material_type,
            success=False,
            error_message=str(exc),
        )

    if file_size > effective_max:
        msg = (
            f"File {artifact.file_path} ({file_size} bytes) exceeds "
            f"max_file_size ({effective_max} bytes) — skipped."
        )
        logger.warning(msg)
        return ExtractionResult(
            file_path=artifact.file_path,
            content="",
            file_format=artifact.file_format,
            project_phase=artifact.project_phase,
            source_material_type=artifact.source_material_type,
            success=False,
            error_message=msg,
        )

    # Route to extractor

    try:
        if extractor_name == "video":
            content = extract_from_video(
                path,
                transcription_config=transcription_config,
                model_config=ocr_model_config,
            )
        elif extractor_name == "pdf":
            content = extract_from_pdf(
                path,
                ocr_enabled=ocr_enabled,
                ocr_provider=ocr_provider,
                ocr_model_config=ocr_model_config,
            )
        elif extractor_name == "pptx":
            content = extract_from_pptx(
                path,
                ocr_enabled=ocr_enabled,
                ocr_model_config=ocr_model_config,
            )
        elif extractor_name == "docx":
            content = extract_from_docx(
                path,
                ocr_enabled=ocr_enabled,
                ocr_model_config=ocr_model_config,
            )
        elif extractor_name in _EXTRACTOR_MAP:
            content = _EXTRACTOR_MAP[extractor_name](path)
        else:
            raise ValueError(f"No extractor for format '{artifact.file_format}'")
    except Exception as exc:
        logger.error("Extraction failed for %s: %s", artifact.file_path, exc)
        return ExtractionResult(
            file_path=artifact.file_path,
            content="",
            file_format=artifact.file_format,
            project_phase=artifact.project_phase,
            source_material_type=artifact.source_material_type,
            success=False,
            error_message=str(exc),
        )

    return ExtractionResult(
        file_path=artifact.file_path,
        content=content,
        file_format=artifact.file_format,
        project_phase=artifact.project_phase,
        source_material_type=artifact.source_material_type,
        success=True,
    )


# ---------------------------------------------------------------------------
# Parallel extraction
# ---------------------------------------------------------------------------


def extract_artifacts_parallel(
    artifacts: list[DiscoveredArtifact],
    max_file_size: int = 30_000_000,
    video_max_file_size: int = 300_000_000,
    transcription_config: dict | None = None,
    max_workers: int = 4,
    ocr_enabled: bool = False,
    ocr_max_pages: int = 50,
    ocr_provider: str = "llm",
    ocr_model_config: dict | None = None,
) -> list[ExtractionResult]:
    """Extract content from multiple artifacts in parallel.

    Uses :class:`~concurrent.futures.ThreadPoolExecutor` with
    *max_workers* threads. Each artifact is independently extracted —
    no shared state between extractors. Failed extractions are logged
    and included in results with ``success=False``.

    When *ocr_enabled* is ``True``, image-only PDF pages are OCR'd using
    the selected *ocr_provider* (``"llm"`` or ``"textract"``), up to
    *ocr_max_pages* total pages per run (0 = unlimited).

    Returns a list of :class:`ExtractionResult` in the same order as
    the input *artifacts* list.
    """
    global _ocr_page_count, _ocr_max_pages

    if not artifacts:
        return []

    # Validate OCR provider
    if ocr_enabled and ocr_provider not in _VALID_OCR_PROVIDERS:
        logger.warning(
            "Unknown artifact_ocr_provider '%s', defaulting to 'llm'.",
            ocr_provider,
        )
        ocr_provider = "llm"

    # Reset OCR counter for this run
    with _ocr_page_lock:
        _ocr_page_count = 0
        _ocr_max_pages = ocr_max_pages

    results: dict[str, ExtractionResult] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_artifact = {
            executor.submit(
                extract_artifact,
                art,
                max_file_size,
                video_max_file_size,
                transcription_config,
                ocr_enabled,
                ocr_provider,
                ocr_model_config,
            ): art
            for art in artifacts
        }

        with tqdm(
            total=len(artifacts), desc="📦 Extracting artifacts", unit="file"
        ) as pbar:
            for future in as_completed(future_to_artifact):
                art = future_to_artifact[future]
                try:
                    result = future.result()
                except Exception as exc:
                    logger.error(
                        "Unexpected error extracting %s: %s",
                        art.file_path,
                        exc,
                    )
                    result = ExtractionResult(
                        file_path=art.file_path,
                        content="",
                        file_format=art.file_format,
                        project_phase=art.project_phase,
                        source_material_type=art.source_material_type,
                        success=False,
                        error_message=str(exc),
                    )
                results[art.file_path] = result
                pbar.update(1)

    # Log OCR usage summary
    if ocr_enabled:
        with _ocr_page_lock:
            used = _ocr_page_count
        limit_str = str(ocr_max_pages) if ocr_max_pages > 0 else "unlimited"
        logger.info(
            "%s OCR pages used this run: %d (limit: %s)",
            ocr_provider.upper(),
            used,
            limit_str,
        )

    # Preserve input order
    return [results[art.file_path] for art in artifacts]
