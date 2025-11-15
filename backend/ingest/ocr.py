"""
Simple OCR module for scanned PDFs and image files.

Uses pytesseract (Tesseract OCR) to extract text from:
- Image-based PDFs (scanned documents)
- Common image formats (JPG, PNG, TIFF)

Gracefully falls back to empty text if pytesseract or Tesseract is unavailable.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    import pytesseract
    from pdf2image import convert_from_path
    HAS_PYTESSERACT = True
except ImportError:
    HAS_PYTESSERACT = False
    logger.warning(
        "pytesseract or pdf2image not installed. OCR support disabled. "
        "Install with: pip install pytesseract pdf2image"
    )


def _detect_scanned_pdf(filepath: str) -> bool:
    """
    Simple heuristic: try to extract text from first page.
    If < 100 chars extracted, likely scanned (image-based).
    """
    if not HAS_PYTESSERACT:
        return False

    try:
        import pypdf
        with open(filepath, 'rb') as f:
            pdf = pypdf.PdfReader(f)
            if len(pdf.pages) == 0:
                return False
            first_page_text = pdf.pages[0].extract_text() or ""
            # If first page has minimal text, likely scanned
            return len(first_page_text.strip()) < 100
    except Exception as e:
        logger.debug(f"Could not detect if PDF is scanned: {e}")
        return False


def ocr_pdf(filepath: str, max_pages: Optional[int] = None) -> Optional[str]:
    """
    Extract text from a scanned PDF using OCR.

    Args:
        filepath: Path to PDF file.
        max_pages: Maximum pages to OCR (None = all). Useful for large PDFs.

    Returns:
        Extracted text or None if OCR fails.
    """
    if not HAS_PYTESSERACT:
        logger.warning(f"OCR not available for {filepath}")
        return None

    try:
        logger.info(f"Performing OCR on PDF: {filepath}")
        
        # Convert PDF pages to images
        images = convert_from_path(filepath)
        
        # Limit pages if specified
        if max_pages:
            images = images[:max_pages]
        
        # Extract text from each image
        text_parts = []
        for i, image in enumerate(images):
            try:
                page_text = pytesseract.image_to_string(image)
                if page_text.strip():
                    text_parts.append(page_text)
            except Exception as e:
                logger.warning(f"OCR failed for page {i+1}: {e}")
        
        text = '\n'.join(text_parts)
        if text.strip():
            logger.info(f"OCR extracted {len(text)} chars from {len(images)} pages")
            return text
        else:
            logger.warning(f"OCR produced empty text for {filepath}")
            return None

    except Exception as e:
        logger.error(f"OCR failed for {filepath}: {e}")
        return None


def ocr_image(filepath: str) -> Optional[str]:
    """
    Extract text from an image file using OCR.

    Args:
        filepath: Path to image file (JPG, PNG, TIFF, etc.).

    Returns:
        Extracted text or None if OCR fails.
    """
    if not HAS_PYTESSERACT:
        logger.warning(f"OCR not available for {filepath}")
        return None

    try:
        logger.info(f"Performing OCR on image: {filepath}")
        text = pytesseract.image_to_string(filepath)
        if text.strip():
            logger.info(f"OCR extracted {len(text)} chars from image")
            return text
        else:
            logger.warning(f"OCR produced empty text for {filepath}")
            return None
    except Exception as e:
        logger.error(f"OCR failed for {filepath}: {e}")
        return None


def is_ocr_available() -> bool:
    """Check if OCR is available (pytesseract + tesseract installed)."""
    if not HAS_PYTESSERACT:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        logger.warning("pytesseract found but Tesseract binary not installed.")
        return False
