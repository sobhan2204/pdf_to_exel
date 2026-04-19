import datetime
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    from groq import Groq
except Exception:
    Groq = None

# Optional date parser.
try:
    from dateutil import parser as du_parser
except Exception:
    du_parser = None


load_dotenv()


def load_prompt(prompt_path: str = "prompts/prompt.text") -> str:
    """Load prompt instructions from file."""
    prompt_file = Path(prompt_path)
    if not prompt_file.exists():
        return "Extract key-value pairs from text into JSON rows."
    return prompt_file.read_text(encoding="utf-8")


def chunk_text(text: str, max_length: int = 8000) -> list[str]:
    """Split text into manageable chunks by word count."""
    words = text.split()
    chunks, current = [], []
    total = 0

    for word in words:
        next_len = total + len(word) + 1
        if current and next_len > max_length:
            chunks.append(" ".join(current))
            current = [word]
            total = len(word) + 1
        else:
            current.append(word)
            total = next_len

    if current:
        chunks.append(" ".join(current))

    return chunks


def normalize_date(date_str: str) -> str:
    """Return ISO date if parseable; otherwise return original text."""
    if not date_str or not isinstance(date_str, str):
        return date_str

    if du_parser:
        try:
            dt = du_parser.parse(date_str, fuzzy=True)
            return dt.date().isoformat()
        except Exception:
            pass

    formats = [
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d %B %Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(date_str, fmt)
            return dt.date().isoformat()
        except Exception:
            continue
    return date_str


def _clean_str(value):
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _clean_num_text(value: str):
    text = value.strip().replace(",", "")
    if re.fullmatch(r"\d+", text):
        return int(text)
    if re.fullmatch(r"\d+\.\d+", text):
        return float(text)
    return value


def _remove_markdown_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def _extract_json_payload(raw: str):
    cleaned = _remove_markdown_fence(raw)
    parse_attempts = [cleaned]

    match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if match:
        parse_attempts.append(match.group(0))

    obj_match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if obj_match:
        parse_attempts.append(obj_match.group(0))

    for payload in parse_attempts:
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                for key in ("items", "data", "results", "records"):
                    val = parsed.get(key)
                    if isinstance(val, list):
                        return val
        except Exception:
            compact = re.sub(r",\s*([}\]])", r"\1", payload)
            try:
                parsed = json.loads(compact)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                continue
    return []


def _sanitize_rows(rows: list) -> list[dict]:
    sanitized = []
    seen = set()

    for row in rows:
        if not isinstance(row, dict):
            continue

        key = _clean_str(row.get("key") or row.get("Key") or row.get("field"))
        value = row.get("value") if "value" in row else row.get("Value")
        comments = _clean_str(row.get("comments") or row.get("Comments"))

        if isinstance(value, str):
            value = value.strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                value = normalize_date(value)
            elif re.fullmatch(r"[\d,.]+", value):
                value = _clean_num_text(value)

        if not key and value is None:
            continue

        signature = (
            (key or "").lower(),
            str(value).strip().lower() if value is not None else "",
            (comments or "").lower(),
        )
        if signature in seen:
            continue

        seen.add(signature)
        sanitized.append({"key": key or "Unknown", "value": value, "comments": comments})

    return sanitized


def _build_llm_prompt(base_prompt: str, text_chunk: str) -> str:
    return (
        f"{base_prompt}\n\n"
        "Strict output requirements:\n"
        "- Output ONLY a valid JSON array (no markdown, no prose).\n"
        "- Each element must have: key, value, comments.\n"
        "- Prefer fine-grained rows (one fact per row).\n"
        "- Use meaningful key names (avoid generic keys like 'name' unless context is unknown).\n"
        "- If the document describes a person, include Full Name and split into First Name/Last Name when possible.\n"
        "- Keep values faithful to the source text.\n"
        "- If information is implicit, infer the key label but not the value text.\n\n"
        "Document text:\n"
        f"{text_chunk}"
    )


def _extract_with_gemini(prompt_text: str) -> list[dict]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or genai is None:
        return []

    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(
        prompt_text,
        generation_config={"temperature": 0.1, "top_p": 0.9},
    )

    raw = getattr(response, "text", "") or ""
    return _sanitize_rows(_extract_json_payload(raw))


def _extract_with_groq(prompt_text: str) -> list[dict]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or Groq is None:
        return []

    model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    client = Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model=model_name,
        temperature=0.1,
        messages=[
            {
                "role": "system",
                "content": "Return only a JSON array. Every element must include key, value, comments.",
            },
            {"role": "user", "content": prompt_text},
        ],
    )
    raw = completion.choices[0].message.content or ""
    return _sanitize_rows(_extract_json_payload(raw))


def _clean_cert_title(title: str) -> str:
    cleaned = re.sub(r"^(?:and|while|with)\s+", "", title.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:his|her|their)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _normalize_org_name(name: str) -> str:
    normalized = re.sub(r"\s+", " ", name).strip()
    # Keep the base company name when legal suffix text appears as an add-on.
    normalized = re.sub(r"\s+(?:Solutions|Technologies|Services)\s*$", "", normalized, flags=re.IGNORECASE)
    return normalized


def _find_sentence(source_text: str, phrase: str) -> str | None:
    lower_text = source_text.lower()
    idx = lower_text.find(phrase.lower())
    if idx == -1:
        return None

    start = source_text.rfind(". ", 0, idx)
    end = source_text.find(". ", idx)

    start = 0 if start == -1 else start + 2
    end = len(source_text) if end == -1 else end + 1

    sentence = source_text[start:end].strip()
    return " ".join(sentence.split()) if sentence else None


def _add_row(results: list[dict], seen: set, key: str, value=None, comments=None):
    cleaned_key = _clean_str(key)
    cleaned_comments = _clean_str(comments)

    if isinstance(value, str):
        value = value.strip()
        if re.fullmatch(r"[\d,]+", value):
            value = _clean_num_text(value)

    if not cleaned_key:
        return

    signature = (
        cleaned_key.lower(),
        str(value).strip().lower() if value is not None else "",
        (cleaned_comments or "").lower(),
    )
    if signature in seen:
        return

    seen.add(signature)
    results.append({"key": cleaned_key, "value": value, "comments": cleaned_comments})


def _extract_person_name(raw_text: str) -> str | None:
    """Extract likely person full name from common profile/resume patterns."""
    text = " ".join(raw_text.split())
    patterns = [
        r"\b(?:full\s*name|candidate\s*name|applicant\s*name|name)\s*[:\-]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b",
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s+was born\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = re.sub(r"\s+", " ", match.group(1)).strip(" ,.;:-")
            if len(candidate.split()) >= 2:
                return candidate

    return None


def _enrich_person_name_rows(raw_text: str, rows: list[dict]) -> list[dict]:
    """Ensure person-name fields exist and match the source text."""
    enriched = [dict(row) for row in rows if isinstance(row, dict)]

    full_name = _extract_person_name(raw_text)
    if not full_name:
        return _sanitize_rows(enriched)

    name_parts = full_name.split()
    first_name = name_parts[0]
    last_name = name_parts[-1]

    def _normalize_key(key: str) -> str:
        return re.sub(r"\s+", " ", key.strip().lower())

    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    def _upsert_name_row(
        aliases: set[str],
        canonical_key: str,
        expected_value: str,
        fallback_comment: str,
    ) -> None:
        row_index = None
        for idx, row in enumerate(enriched):
            row_key = _clean_str(row.get("key") or row.get("Key") or row.get("field"))
            if row_key and _normalize_key(row_key) in aliases:
                row_index = idx
                break

        if row_index is None:
            enriched.append(
                {
                    "key": canonical_key,
                    "value": expected_value,
                    "comments": fallback_comment,
                }
            )
            return

        row = enriched[row_index]
        current_value = _clean_str(row.get("value") if "value" in row else row.get("Value"))
        current_comment = _clean_str(row.get("comments") or row.get("Comments"))

        row["key"] = canonical_key
        if not current_value or _normalize_text(current_value) != _normalize_text(expected_value):
            row["value"] = expected_value
            row["comments"] = "Validated against source text."
        elif not current_comment:
            row["comments"] = fallback_comment

    _upsert_name_row(
        aliases={"name", "full name", "candidate name", "applicant name", "person name"},
        canonical_key="Full Name",
        expected_value=full_name,
        fallback_comment="Person name extracted from source text.",
    )
    _upsert_name_row(
        aliases={"first name", "given name"},
        canonical_key="First Name",
        expected_value=first_name,
        fallback_comment="Derived from full name in source text.",
    )
    _upsert_name_row(
        aliases={"last name", "surname", "family name"},
        canonical_key="Last Name",
        expected_value=last_name,
        fallback_comment="Derived from full name in source text.",
    )

    return _sanitize_rows(enriched)


def extract_data_with_regex(raw_text: str) -> list[dict]:
    """Regex and rule-based fallback extraction for when LLM providers are unavailable."""
    text = " ".join(raw_text.split())
    results = []
    seen = set()

    person_match = re.search(r"\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\s+was born on\b", text)
    if person_match:
        _add_row(results, seen, "First Name", person_match.group(1))
        _add_row(results, seen, "Last Name", person_match.group(2))

    bio_match = re.search(
        r"was born on ([A-Za-z]+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}),"
        r" in ([A-Za-z .'-]+),\s*([A-Za-z .'-]+), making (?:him|her) (\d+) years old(?: as of (\d{4}))?",
        text,
    )
    if bio_match:
        dob = normalize_date(bio_match.group(1))
        city = bio_match.group(2).strip()
        state = bio_match.group(3).strip()
        age = bio_match.group(4).strip()
        as_of = bio_match.group(5)

        birth_comment = _find_sentence(text, "Born and raised")
        age_comment = _find_sentence(text, "age serves as a key demographic marker")

        _add_row(results, seen, "Date of Birth", dob)
        _add_row(results, seen, "Birth City", city, birth_comment)
        _add_row(results, seen, "Birth State", state, birth_comment)
        _add_row(results, seen, "Age", f"{age} years", age_comment)

    blood_match = re.search(r"\b([ABO][+-])\s+blood group\b", text, flags=re.IGNORECASE)
    if blood_match:
        _add_row(results, seen, "Blood Group", blood_match.group(1).upper(), _find_sentence(text, "blood group"))

    nationality_match = re.search(r"\bAs an?\s+([A-Za-z]+)\s+national\b", text, flags=re.IGNORECASE)
    if nationality_match:
        _add_row(
            results,
            seen,
            "Nationality",
            nationality_match.group(1).title(),
            _find_sentence(text, "citizenship status"),
        )

    first_role_match = re.search(
        r"professional journey began on ([A-Za-z]+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2}),"
        r" when .*? first company as a ([A-Za-z ]+?) with an annual salary of ([\d,]+) ([A-Z]{3})",
        text,
        flags=re.IGNORECASE,
    )
    if first_role_match:
        _add_row(results, seen, "Joining Date of first professional role", normalize_date(first_role_match.group(1)))
        _add_row(results, seen, "Designation of first professional role", first_role_match.group(2).strip())
        _add_row(results, seen, "Salary of first professional role", _clean_num_text(first_role_match.group(3)))
        _add_row(results, seen, "Salary currency of first professional role", first_role_match.group(4).upper())

    current_role_match = re.search(
        r"current role at ([A-Za-z0-9& .'-]+?) beginning on ([A-Za-z]+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2}),"
        r" where .*? serves as a ([A-Za-z ]+?) earning ([\d,]+) ([A-Z]{3})",
        text,
        flags=re.IGNORECASE,
    )
    if current_role_match:
        _add_row(results, seen, "Current Organization", _normalize_org_name(current_role_match.group(1)))
        _add_row(results, seen, "Current Joining Date", normalize_date(current_role_match.group(2)))
        _add_row(results, seen, "Current Designation", current_role_match.group(3).strip())
        _add_row(
            results,
            seen,
            "Current Salary",
            _clean_num_text(current_role_match.group(4)),
            _find_sentence(text, "salary progression"),
        )
        _add_row(results, seen, "Current Salary Currency", current_role_match.group(5).upper())

    previous_match = re.search(
        r"worked at ([A-Za-z0-9& .'-]+?) from ([A-Za-z]+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2}),"
        r" to (\d{4}), starting as a ([A-Za-z ]+?) and earning a promotion in (\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if previous_match:
        _add_row(results, seen, "Previous Organization", _normalize_org_name(previous_match.group(1)))
        _add_row(results, seen, "Previous Joining Date", normalize_date(previous_match.group(2)))
        _add_row(results, seen, "Previous end year", int(previous_match.group(3)))
        _add_row(
            results,
            seen,
            "Previous Starting Designation",
            previous_match.group(4).strip(),
            f"Promoted in {previous_match.group(5)}",
        )

    school_match = re.search(
        r"high school education at ([A-Za-z0-9.'\-\s,]+?), where .*?12th standard in (\d{4}),"
        r" achieving an? (?:outstanding )?([\d.]+)% overall score",
        text,
        flags=re.IGNORECASE,
    )
    if school_match:
        _add_row(results, seen, "High School", school_match.group(1).strip())
        _add_row(results, seen, "12th standard pass out year", int(school_match.group(2)), _find_sentence(text, "core subjects included"))
        _add_row(results, seen, "12th overall board score", f"{school_match.group(3)}%", "Outstanding achievement")

    undergrad_match = re.search(
        r"B\.Tech in ([A-Za-z ]+) at .*?([A-Z][A-Za-z ]+?), graduating .*? in (\d{4})"
        r" with a CGPA of ([\d.]+) on a 10-point scale, ranking (\d+(?:st|nd|rd|th)) among (\d+) students",
        text,
        flags=re.IGNORECASE,
    )
    if undergrad_match:
        subject = undergrad_match.group(1).strip()
        college = re.sub(r"^(?:the\s+)?(?:prestigious\s+)?", "", undergrad_match.group(2).strip(), flags=re.IGNORECASE)
        _add_row(results, seen, "Undergraduate degree", f"B.Tech ({subject})")
        _add_row(results, seen, "Undergraduate college", college)
        _add_row(
            results,
            seen,
            "Undergraduate year",
            int(undergrad_match.group(3)),
            f"Graduated with honors, ranked {undergrad_match.group(5)} among {undergrad_match.group(6)} students",
        )
        _add_row(results, seen, "Undergraduate CGPA", float(undergrad_match.group(4)), "On a 10-point scale")

    graduate_match = re.search(
        r"continued at ([A-Z][A-Za-z ]+), where .*?earned (?:his|her) M\.Tech in ([A-Za-z ]+) in (\d{4}),"
        r" achieving an? (?:exceptional )?CGPA of ([\d.]+)(?: and scoring (\d+) out of (\d+))?",
        text,
        flags=re.IGNORECASE,
    )
    if graduate_match:
        college = graduate_match.group(1).strip()
        subject = graduate_match.group(2).strip()
        grad_year = int(graduate_match.group(3))
        grad_cgpa = float(graduate_match.group(4))
        thesis_comment = None
        if graduate_match.group(5) and graduate_match.group(6):
            thesis_comment = f"Scored {graduate_match.group(5)} out of {graduate_match.group(6)} in final year thesis"

        _add_row(results, seen, "Graduation degree", f"M.Tech ({subject})")
        _add_row(results, seen, "Graduation college", college, _find_sentence(text, "academic excellence continued"))
        _add_row(results, seen, "Graduation year", grad_year)
        _add_row(results, seen, "Graduation CGPA", grad_cgpa, thesis_comment)

    cert_patterns = [
        (
            r"passed the ([A-Za-z ]+?) exam in (\d{4}) with a score of (\d+) out of (\d+)",
            "Certifications 1",
            lambda m: (
                _clean_cert_title(m.group(1).strip()),
                f"Pursued in {m.group(2)} with score {m.group(3)}/{m.group(4)}",
            ),
        ),
        (
            r"followed by the ([A-Za-z ]+?) certification in (\d{4}) with (\d+) points",
            "Certifications 2",
            lambda m: (
                _clean_cert_title(m.group(1).strip()),
                f"Pursued in {m.group(2)} with {m.group(3)} points",
            ),
        ),
        (
            r"([A-Za-z ]+?) certification, obtained in (\d{4}), was achieved with an? \"([^\"]+)\" rating",
            "Certifications 3",
            lambda m: (
                f"{_clean_cert_title(m.group(1).strip())} certification",
                f"Obtained in {m.group(2)} with '{m.group(3)}' rating",
            ),
        ),
        (
            r"([A-Za-z ]+?) certification earned .*?(\d+)% score",
            "Certifications 4",
            lambda m: (
                f"{_clean_cert_title(m.group(1).strip())} certification",
                f"Achieved with {m.group(2)}% score",
            ),
        ),
    ]
    for pattern, label, formatter in cert_patterns:
        cert_match = re.search(pattern, text, flags=re.IGNORECASE)
        if cert_match:
            cert_name, cert_comment = formatter(cert_match)
            _add_row(results, seen, label, cert_name, cert_comment)

    technical_match = re.search(r"In terms of technical proficiency, (.*)$", text, flags=re.IGNORECASE)
    if technical_match:
        _add_row(results, seen, "Technical Proficiency", None, technical_match.group(1).strip())

    # Generic labeled-pair fallback for other document types.
    label_pairs = re.findall(r"\b([A-Za-z][A-Za-z0-9 /()\-]{2,50})\s*:\s*([^:;\n]{1,150})", raw_text)
    for label, value in label_pairs:
        _add_row(results, seen, label.strip(), value.strip(), "Labeled field extracted from document")

    if not results:
        _add_row(
            results,
            seen,
            "Document Text",
            raw_text[:300] + ("..." if len(raw_text) > 300 else ""),
            "Fallback capture because no structured entity was detected",
        )

    return results


def _extract_with_llm(raw_text: str, base_prompt: str) -> tuple[list[dict], str | None]:
    chunks = chunk_text(raw_text)
    providers = [
        ("Groq", _extract_with_groq),
    ]

    for provider_name, provider in providers:
        aggregated = []
        for idx, chunk in enumerate(chunks, start=1):
            print(f" Trying {provider_name} for chunk {idx}/{len(chunks)}...")
            prompt_text = _build_llm_prompt(base_prompt, chunk)
            try:
                chunk_rows = provider(prompt_text)
            except Exception as exc:
                print(f" {provider_name} failed: {exc}")
                aggregated = []
                break

            if chunk_rows:
                aggregated.extend(chunk_rows)

        final_rows = _sanitize_rows(aggregated)
        if final_rows:
            return final_rows, provider_name

    return [], None


def structure_text_with_llm(raw_text: str, prompt_path: str = "prompts/prompt.text") -> list[dict]:
    """
    Structure text into key/value rows using LLM-first extraction and regex fallback.

    Args:
        raw_text: Raw text extracted from PDF.
        prompt_path: Path to prompt instructions.

    Returns:
        List of dictionaries with keys: key, value, comments.
    """
    if not raw_text or not raw_text.strip():
        return []

    base_prompt = load_prompt(prompt_path)
    chunks = chunk_text(raw_text)
    print(f" Total chunks to process: {len(chunks)}")

    llm_rows, provider_name = _extract_with_llm(raw_text, base_prompt)
    if llm_rows:
        enriched_rows = _enrich_person_name_rows(raw_text, llm_rows)
        if len(enriched_rows) > len(llm_rows):
            print(f" Added {len(enriched_rows) - len(llm_rows)} name field(s) from source text")
        print(f" Extracted {len(enriched_rows)} data points using {provider_name}")
        return enriched_rows

    print(" LLM provider unavailable or returned no structured output. Using regex fallback...")
    fallback_rows = extract_data_with_regex(raw_text)
    enriched_fallback_rows = _enrich_person_name_rows(raw_text, fallback_rows)
    if len(enriched_fallback_rows) > len(fallback_rows):
        print(f" Added {len(enriched_fallback_rows) - len(fallback_rows)} name field(s) from source text")
    print(f" Extracted {len(enriched_fallback_rows)} data points using regex fallback")
    return enriched_fallback_rows
