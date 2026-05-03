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


def clean_str(value):
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def clean_num_text(value: str):
    text = value.strip().replace(",", "")
    if re.fullmatch(r"\d+", text):
        return int(text)
    if re.fullmatch(r"\d+\.\d+", text):
        return float(text)
    return value


def remove_markdown_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def extract_json_payload(raw: str):
    cleaned = remove_markdown_fence(raw)
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


def sanitize_rows(rows: list) -> list[dict]:
    sanitized = []
    seen = set()

    for row in rows:
        if not isinstance(row, dict):
            continue

        key = clean_str(row.get("key") or row.get("Key") or row.get("field"))
        value = row.get("value") if "value" in row else row.get("Value")
        comments = clean_str(row.get("comments") or row.get("Comments"))

        if isinstance(value, str):
            value = value.strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                value = normalize_date(value)
            elif re.fullmatch(r"[\d,.]+", value):
                value = clean_num_text(value)

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


def build_llm_prompt(base_prompt: str, text_chunk: str, job_desc: str = "") -> str:
    job_context = ""
    if job_desc:
        job_context = (
            "JOB EVALUATION INSTRUCTIONS (CRITICAL):\n"
            "You must cross-reference the candidate's text against the JOB REQUIREMENTS below.\n"
            "JOB REQUIREMENTS:\n"
            f"{job_desc}\n\n"
            "You MUST extract skills into exactly these three categories, creating a SEPARATE row for each skill:\n"
            "1. MATCHED SKILLS (Candidate has this required skill):\n"
            "   -> { \"key\": \"Matched Skill\", \"value\": \"[Skill Name]\", \"comments\": \"Proficiency: [Mention their rating, level, or years of exp from text]\" }\n"
            "2. MISSING SKILLS (Skill is in the job requirements, but candidate DOES NOT have it):\n"
            "   -> { \"key\": \"Missing Skill\", \"value\": \"[Skill Name]\", \"comments\": \"Required by job but not found in profile.\" }\n"
            "3. ADDITIONAL SKILLS (Candidate has this skill, but it is NOT in the job requirements):\n"
            "   -> { \"key\": \"Additional Skill\", \"value\": \"[Skill Name]\", \"comments\": \"Proficiency: [Mention their rating, level, or years of exp from text]\" }\n\n"
            "4. Add an 'Efficacy Score' row calculating match percentage with reasoning in comments.\n\n"
        )

    return (
        f"{base_prompt}\n\n"
        f"{job_context}"
        "CRITICAL FORMATTING RULES:\n"
        "- Output ONLY a valid JSON array (no markdown, no prose).\n"
        "- Each element must have exactly these keys: key, value, comments.\n"
        "- SPLIT LISTS: Never use comma-separated lists in the 'value' field. If there are multiple items (like skills, tools, or locations), create a SEPARATE JSON object for EACH item.\n"
        "- EXTREME CONCISENESS: The 'value' field MUST be 1-4 words (just the name, number, or short phrase). Absolutely NO full sentences.\n"
        "- If the document describes a person, include Full Name and split into First Name/Last Name when possible.\n\n"
        "Document text:\n"
        f"{text_chunk}"
    )




def extract_with_groq(prompt_text: str) -> list[dict]:
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
    return sanitize_rows(extract_json_payload(raw))


def clean_cert_title(title: str) -> str:
    cleaned = re.sub(r"^(?:and|while|with)\s+", "", title.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:his|her|their)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def normalize_org_name(name: str) -> str:
    normalized = re.sub(r"\s+", " ", name).strip()
    normalized = re.sub(r"\s+(?:Solutions|Technologies|Services)\s*$", "", normalized, flags=re.IGNORECASE)
    return normalized


def add_row(results: list[dict], seen: set, key: str, value=None, comments=None):
    cleaned_key = clean_str(key)
    cleaned_comments = clean_str(comments)

    if isinstance(value, str):
        value = value.strip()
        if re.fullmatch(r"[\d,]+", value):
            value = clean_num_text(value)

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


def extract_person_name(raw_text: str) -> str | None:
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


def enrich_person_name_rows(raw_text: str, rows: list[dict]) -> list[dict]:
    enriched = [dict(row) for row in rows if isinstance(row, dict)]

    full_name = extract_person_name(raw_text)
    if not full_name:
        return sanitize_rows(enriched)

    name_parts = full_name.split()
    first_name = name_parts[0]
    last_name = name_parts[-1]

    def normalize_key(key: str) -> str:
        return re.sub(r"\s+", " ", key.strip().lower())

    def normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    def upsert_name_row(aliases: set[str], canonical_key: str, expected_value: str, fallback_comment: str):
        row_index = None
        for idx, row in enumerate(enriched):
            row_key = clean_str(row.get("key") or row.get("Key") or row.get("field"))
            if row_key and normalize_key(row_key) in aliases:
                row_index = idx
                break

        if row_index is None:
            enriched.append({"key": canonical_key, "value": expected_value, "comments": fallback_comment})
            return

        row = enriched[row_index]
        current_value = clean_str(row.get("value") if "value" in row else row.get("Value"))
        current_comment = clean_str(row.get("comments") or row.get("Comments"))

        row["key"] = canonical_key
        if not current_value or normalize_text(current_value) != normalize_text(expected_value):
            row["value"] = expected_value
            row["comments"] = "Validated against source text."
        elif not current_comment:
            row["comments"] = fallback_comment

    upsert_name_row({"name", "full name", "candidate name", "person name"}, "Full Name", full_name, "Extracted from source.")
    upsert_name_row({"first name", "given name"}, "First Name", first_name, "Derived from full name.")
    upsert_name_row({"last name", "surname", "family name"}, "Last Name", last_name, "Derived from full name.")

    return sanitize_rows(enriched)


def extract_data_with_regex(raw_text: str) -> list[dict]:
    """Regex and rule-based fallback extraction for when LLM providers are unavailable."""
    text = " ".join(raw_text.split())
    results = []
    seen = set()

    person_match = re.search(r"\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\s+was born on\b", text)
    if person_match:
        add_row(results, seen, "First Name", person_match.group(1))
        add_row(results, seen, "Last Name", person_match.group(2))

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

        add_row(results, seen, "Date of Birth", dob)
        add_row(results, seen, "Birth City", city, "City of birth")
        add_row(results, seen, "Birth State", state, "State of birth")
        add_row(results, seen, "Age", f"{age} years")

    blood_match = re.search(r"\b([ABO][+-])\s+blood group\b", text, flags=re.IGNORECASE)
    if blood_match:
        add_row(results, seen, "Blood Group", blood_match.group(1).upper())

    technical_match = re.search(r"In terms of technical proficiency, (.*)$", text, flags=re.IGNORECASE)
    if technical_match:
        skills_raw = technical_match.group(1).strip()
        for skill in re.split(r',|\band\b', skills_raw):
            cleaned_skill = skill.strip(" .")
            if cleaned_skill:
                add_row(results, seen, "Skill", cleaned_skill)

    if not results:
        add_row(results, seen, "Document Text", raw_text[:300] + ("..." if len(raw_text) > 300 else ""), "Fallback capture")

    return results


def extract_with_llm(raw_text: str, base_prompt: str, job_desc: str = "") -> tuple[list[dict], str | None]:
    chunks = chunk_text(raw_text)
    providers = [
        ("Groq", extract_with_groq),
    ]

    for provider_name, provider in providers:
        aggregated = []
        for idx, chunk in enumerate(chunks, start=1):
            print(f" Trying {provider_name} for chunk {idx}/{len(chunks)}...")
            prompt_text = build_llm_prompt(base_prompt, chunk, job_desc)
            try:
                chunk_rows = provider(prompt_text)
            except Exception as exc:
                print(f" {provider_name} failed: {exc}")
                aggregated = []
                break

            if chunk_rows:
                aggregated.extend(chunk_rows)

        final_rows = sanitize_rows(aggregated)
        if final_rows:
            return final_rows, provider_name

    return [], None


def structure_text_with_llm(raw_text: str, prompt_path: str = "prompts/prompt.text", job_desc: str = "") -> list[dict]:
    """
    Structure text into key/value rows using LLM-first extraction and regex fallback.
    """
    if not raw_text or not raw_text.strip():
        return []

    base_prompt = load_prompt(prompt_path)
    chunks = chunk_text(raw_text)
    print(f" Total chunks to process: {len(chunks)}")

    llm_rows, provider_name = extract_with_llm(raw_text, base_prompt, job_desc)
    
    if llm_rows:
        enriched_rows = enrich_person_name_rows(raw_text, llm_rows)
        
        # Cross-Validation Step: Prevent False "Missing Skills"
        # If a skill was marked Matched anywhere in the document, it cannot be Missing.
        matched_skills = {str(r.get("value")).strip().lower() for r in enriched_rows if r.get("key") == "Matched Skill"}
        
        final_validated_rows = []
        for r in enriched_rows:
            if r.get("key") == "Missing Skill":
                val = str(r.get("value")).strip().lower()
                if val in matched_skills:
                    continue  # Skip it, we found it!
            final_validated_rows.append(r)
            
        if len(final_validated_rows) > len(llm_rows):
            print(f" Added {len(final_validated_rows) - len(llm_rows)} name field(s) from source text")
        print(f" Extracted {len(final_validated_rows)} data points using {provider_name}")
        return final_validated_rows

    print(" LLM provider unavailable or returned no structured output. Using regex fallback...")
    fallback_rows = extract_data_with_regex(raw_text)
    enriched_fallback_rows = enrich_person_name_rows(raw_text, fallback_rows)
    if len(enriched_fallback_rows) > len(fallback_rows):
        print(f" Added {len(enriched_fallback_rows) - len(fallback_rows)} name field(s) from source text")
    print(f" Extracted {len(enriched_fallback_rows)} data points using regex fallback")
    return enriched_fallback_rows