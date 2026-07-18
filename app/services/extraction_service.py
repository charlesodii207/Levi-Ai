import io
from typing import Optional


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF file."""
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text.strip()
    except Exception as e:
        return f"[PDF extraction error: {str(e)}]"


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text from Word document."""
    try:
        import docx
        doc = docx.Document(io.BytesIO(file_bytes))
        text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
        return text.strip()
    except Exception as e:
        return f"[DOCX extraction error: {str(e)}]"


def extract_text_from_txt(file_bytes: bytes) -> str:
    """Extract text from plain text file."""
    try:
        return file_bytes.decode("utf-8", errors="ignore").strip()
    except Exception as e:
        return f"[TXT extraction error: {str(e)}]"


def extract_text_from_image(file_bytes: bytes) -> str:
    """Extract text from image using OCR."""
    try:
        import pytesseract
        from PIL import Image
        image = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(image)
        return text.strip()
    except Exception as e:
        return f"[Image OCR error: {str(e)}]"


def extract_text(file_bytes: bytes, filename: str, content_type: str) -> str:
    """
    Extract text from any supported file type.
    Dispatches to the right extractor based on file type.
    """
    filename_lower = filename.lower()
    content_type_lower = content_type.lower()

    if filename_lower.endswith(".pdf") or "pdf" in content_type_lower:
        return extract_text_from_pdf(file_bytes)

    elif filename_lower.endswith(".docx") or "wordprocessingml" in content_type_lower:
        return extract_text_from_docx(file_bytes)

    elif filename_lower.endswith(".txt") or "text/plain" in content_type_lower:
        return extract_text_from_txt(file_bytes)

    elif any(filename_lower.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"]) or "image" in content_type_lower:
        return extract_text_from_image(file_bytes)

    else:
        # Try plain text as fallback
        return extract_text_from_txt(file_bytes)


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100) -> list[str]:
    """
    Split text into overlapping chunks for better search coverage.
    """
    if not text or len(text) < chunk_size:
        return [text] if text else []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap

    return chunks


def search_chunks(query: str, chunks: list[str], top_k: int = 3) -> list[str]:
    """
    Simple keyword-based search through chunks.
    Returns the most relevant chunks for the query.
    """
    if not chunks:
        return []

    query_words = set(query.lower().split())

    scored = []
    for chunk in chunks:
        chunk_lower = chunk.lower()
        score = sum(1 for word in query_words if word in chunk_lower)
        scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for score, chunk in scored[:top_k] if score > 0]
