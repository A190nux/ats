# Document Ingestion Pipeline

The `backend/ingest/` module provides a robust, format-agnostic document loader and OCR support for the ATS system.

## Features

### Document Loader (`loader.py`)

Supports multiple formats with automatic detection and graceful degradation:
- **PDF** — via `pypdf` (with automatic OCR fallback for scanned documents)
- **DOCX** — via `python-docx`
- **DOC** (legacy Word) — via `mammoth` (with fallback to `striprtf` for RTF content)
- **TXT** — plain text files
- **Images** (JPG, PNG, TIFF) — via pytesseract OCR

### OCR Module (`ocr.py`)

Handles text extraction from image-based documents:
- Automatic detection of scanned PDFs (heuristic: < 100 chars extracted)
- OCR fallback for scanned PDFs and image files
- Graceful degradation if pytesseract/Tesseract unavailable
- Optional per-format control via `enable_ocr` flag

## Usage

```python
from backend.ingest.loader import load_documents

# Load all supported formats with OCR fallback for scanned PDFs
docs = load_documents('./cv_uploads', enable_ocr=True)

# Load specific formats only
docs = load_documents('./cv_uploads', 
                     supported_formats=['.pdf', '.docx', '.txt'],
                     enable_ocr=True)

# Disable OCR (faster loading, skips image-based PDFs)
docs = load_documents('./cv_uploads', enable_ocr=False)

# Each document is a llama_index.core.Document with metadata
for doc in docs:
    print(f"{doc.metadata['file_name']}: {len(doc.text)} chars (type: {doc.metadata['file_type']})")
```

## Dependencies

### Required
- `pypdf` — PDF text extraction
- `llama-index-core` — Document abstraction

### Optional (with graceful fallback)
- `python-docx` — DOCX file support
- `mammoth` — Legacy DOC file support
- `striprtf` — RTF fallback for DOC files
- `pdf2image` — Convert PDF pages to images for OCR
- `pytesseract` — Python wrapper for Tesseract OCR
- **Tesseract binary** — Required for OCR (install separately)

Install all optional dependencies:
```bash
pip install python-docx mammoth striprtf pdf2image pytesseract
```

### Tesseract Installation (for OCR)

**Ubuntu/Debian:**
```bash
sudo apt-get install tesseract-ocr
```

**macOS:**
```bash
brew install tesseract
```

**Windows:**
Download from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki)

## Architecture

### Document Loader (`loader.py`)
- Modular format-specific functions: `_load_pdf()`, `_load_docx()`, `_load_doc()`, `_load_txt()`, `_load_image()`
- Main orchestrator: `load_documents(directory, supported_formats, enable_ocr)`
- Returns list of llama_index Documents with standardized metadata

### OCR Module (`ocr.py`)
- `ocr_pdf(filepath, max_pages)` — Extract text from scanned PDF via OCR
- `ocr_image(filepath)` — Extract text from image file
- `_detect_scanned_pdf(filepath)` — Heuristic to detect image-based PDFs
- `is_ocr_available()` — Check if Tesseract is installed

## Testing

Unit tests are provided in `tests.py`:

```bash
cd /home/aly/ats
python3 -m unittest backend.ingest.tests -v
```

Tests cover:
- Loading individual formats (TXT, DOCX)
- Mixed format loading
- Metadata attachment
- Error handling (nonexistent directories)
- OCR availability detection
- OCR disable flag

All 7 tests pass with graceful fallback when dependencies are unavailable.

## Queue-Based Ingestion System

**Status:** ✅ COMPLETE — All 10 tests passing

The queue system enables asynchronous job processing with automatic retries and persistence:

```python
# Enqueue a job
queue = IngestionQueue()
job_id = queue.enqueue("./cv_uploads", max_retries=3)

# Check status
job = queue.get_job(job_id)
print(f"Status: {job.status}, Documents: {job.result}")

# Worker processes jobs (in separate process/thread)
from backend.ingest.worker import run_worker
run_worker()  # Polls queue, processes, retries on error
```

Features:
- SQLite persistence (no external dependencies)
- Automatic retry with configurable max retries
- Job status tracking (pending → processing → completed/failed)
- Result serialization (documents_loaded, metadata, etc.)
- Worker polling with configurable interval

See `QUEUE.md` for deployment and detailed API.

## Integration with Ingestion Pipeline

`ingest_simplified.py` uses the loader with OCR support:

```python
from backend.ingest.loader import load_documents

# Load documents with OCR fallback
documents = load_documents("./cv_uploads/", enable_ocr=True)
```

## Graceful Degradation

If optional dependencies are missing:
- **python-docx missing**: DOCX files skipped with warning
- **mammoth missing**: DOC files attempted via striprtf
- **striprtf missing**: DOC files skipped with warning
- **pdf2image/pytesseract missing**: Scanned PDFs skipped, fallback to regular extraction
- **Tesseract binary missing**: OCR disabled, regular extraction used

Application continues running with reduced capabilities.

## Configuration

Control behavior via function parameters:

```python
# Enable/disable OCR
load_documents(dir, enable_ocr=True)   # Use OCR for scanned PDFs & images
load_documents(dir, enable_ocr=False)  # Skip OCR, faster loading

# Specify formats
load_documents(dir, supported_formats=['.pdf', '.txt'])  # PDF & TXT only
```

## Performance Notes

- **Scanned PDF detection**: ~50ms per PDF (first page extraction)
- **OCR per page**: ~1-3 seconds depending on image quality and resolution
- **Recommendation**: Use `enable_ocr=False` for bulk loading of known digital PDFs, enable for mixed batches

## Future Enhancements

- Batch OCR processing with parallelization
- Language detection and multi-language OCR
- Confidence scoring for OCR text quality
- Caching of OCR results
- Integration with cloud OCR services (AWS Textract, Google Vision) for scale
