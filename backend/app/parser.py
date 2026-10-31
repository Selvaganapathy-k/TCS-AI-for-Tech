from pathlib import Path
import io, fitz
from docx import Document

def parse_file(name, data):
    ext = Path(name).suffix.lower()
    if ext == ".pdf":
        pdf = fitz.open(stream=data, filetype="pdf")
        return "\n".join(p.get_text() for p in pdf)
    if ext == ".docx":
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    if ext in [".txt",".md",".csv",".log"]:
        return data.decode("utf-8", errors="replace")
    raise ValueError("Supported formats: PDF, DOCX, TXT, MD, CSV, LOG")
