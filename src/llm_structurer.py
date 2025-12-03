import json
import re
from pathlib import Path


def load_prompt(prompt_path: str = "prompts/prompt.text") -> str:
    """Load prompt instructions from file."""
    prompt_file = Path(prompt_path)
    if not prompt_file.exists():
        return "Extract all key:value pairs from the text."
    return prompt_file.read_text(encoding="utf-8")


def chunk_text(text: str, max_length: int = 3000) -> list:
    """Split text into manageable chunks."""
    words = text.split()
    chunks, current = [], []
    total = 0
    
    for word in words:
        if total + len(word) > max_length:
            chunks.append(" ".join(current))
            current = []
            total = 0
        
        current.append(word)
        total += len(word) + 1
    
    if current:
        chunks.append(" ".join(current))
    
    return chunks


def extract_data_from_chunk(chunk: str) -> list:
    """Extract structured data using regex patterns."""
    results = []
    
    date_patterns = [
        (r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', "Date extracted from document"),
        (r'(\w+\s+\d{1,2},\s+\d{4})', "Date extracted from document"),
        (r'(\d{4}-\d{2}-\d{2})', "Date extracted from document")
    ]
    for pattern, comment in date_patterns:
        dates = re.findall(pattern, chunk)
        for date in dates:
            results.append({
                "key": "date",
                "value": date,
                "comments": comment
            })
    
    name_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'
    names = re.findall(name_pattern, chunk)
    for name in names:
        if len(name.split()) >= 2:
            results.append({
                "key": "name",
                "value": name,
                "comments": "Name extracted from document"
            })
    
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, chunk)
    for email in emails:
        results.append({
            "key": "email",
            "value": email,
            "comments": "Email address"
        })
    
    phone_pattern = r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
    phones = re.findall(phone_pattern, chunk)
    for phone in phones:
        results.append({
            "key": "phone",
            "value": phone,
            "comments": "Phone number"
        })
    
  
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, chunk)
    for url in urls:
        results.append({
            "key": "url",
            "value": url,
            "comments": "URL found in document"
        })
    

    number_pattern = r'([A-Za-z\s]+):\s*(\d+(?:\.\d+)?)'
    numbers = re.findall(number_pattern, chunk)
    for label, value in numbers:
        results.append({
            "key": label.strip(),
            "value": value,
            "comments": "Numerical value with label"
        })

    if not results:
        results.append({
            "key": "raw_text",
            "value": chunk[:200] + ("..." if len(chunk) > 200 else ""),
            "comments": "Raw text chunk - no specific patterns matched"
        })
    
    return results


def structure_text_with_llm(raw_text: str, prompt_path: str = "prompts/prompt.text") -> list:
    """
    Structure text into key:value pairs with comments.
    
    Args:
        raw_text: Raw text extracted from PDF
        prompt_path: Path to prompt file
        
    Returns:
        List of dictionaries with keys: key, value, comments
    """
    base_prompt = load_prompt(prompt_path)
    chunks = chunk_text(raw_text)
    
    print(f" Total chunks to process: {len(chunks)}")
    
    final_results = []
    
    for i, chunk in enumerate(chunks):
        print(f"➡ Processing chunk {i+1}/{len(chunks)}...")
        chunk_output = extract_data_from_chunk(chunk)
        
        if not isinstance(chunk_output, list):
            raise ValueError("Extraction must return a list.")
        
        final_results.extend(chunk_output)
    
    print(f" Extracted {len(final_results)} data points")
    return final_results
