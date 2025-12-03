import pdfplumber
from pathlib import Path


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract raw text from PDF without any cleaning.
    Args:
        pdf_path: Path to the PDF file
    Returns:
        Raw extracted text as a single string
    """
    extracted_text = []
    
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                extracted_text.append(text)
    
    return " ".join(extracted_text)
