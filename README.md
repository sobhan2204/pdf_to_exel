# AI Document Structurer

Convert an unstructured PDF into a structured Excel sheet using an LLM (Groq API) with a regex fallback.

## What this project does

The pipeline reads text from a PDF, structures it into rows of:

- `key`
- `value`
- `comments`

Then it writes those rows into `data/output/Output.xlsx`.

## How the pipeline works

1. Extract text from PDF using `pdfplumber`.
2. Send text to Groq LLM with strict JSON instructions.
3. Parse and sanitize LLM JSON output.
4. Enrich key fields (for example name fields) if needed.
5. Fall back to regex extraction if LLM is unavailable.
6. Write final structured rows to Excel.

## Project structure and what each file does

| Path | Purpose |
| --- | --- |
| `src/main.py` | Main entry point for the pipeline. Handles CLI args, selects input PDF, runs extract -> structure -> excel write. |
| `src/extract.py` | Reads PDF and returns raw text content. |
| `src/llm_structurer.py` | Core structuring logic: prompt loading, Groq call, JSON parsing, dedupe/sanitize, name enrichment, regex fallback. |
| `src/excel_writer.py` | Writes structured rows to Excel (`#`, `Key`, `Value`, `Comments`) with formatting. |
| `prompts/prompt.text` | Prompt template used for LLM extraction behavior. |
| `data/input/` | Place input PDF files here. |
| `data/output/` | Contains generated output Excel files. |
| `data/output/Expected Output.xlsx` | Reference sample output. |
| `data/output/Output.xlsx` | Actual generated output from the latest run. |
| `requirements.txt` | Pip install dependencies. |
| `pyproject.toml` | Project metadata and dependency definitions (PEP 621 style). |
| `main.py` | Root-level placeholder script (not the pipeline entry point). |
| `uv.lock` | Lockfile for uv-managed dependency resolution. |

## Prerequisites

- Python 3.12+
- A Groq API key

## Setup

1. Create and activate virtual environment (optional but recommended).
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Add `.env` file at project root with:

```env
GROQ_API_KEY=your_groq_api_key_here
```

Optional:

```env
GROQ_MODEL=llama-3.3-70b-versatile
```

## How to run

### Default mode (auto-select input)

If no `--pdf` is provided, the newest PDF in `data/input/` is used.

```bash
python src/main.py
```

### Explicit input PDF

```bash
python src/main.py --pdf "data/input/job_application.pdf"
```

### Custom output path

```bash
python src/main.py --pdf "data/input/job_application.pdf" --output "data/output/MyOutput.xlsx"
```

### Custom prompt file

```bash
python src/main.py --prompt "prompts/prompt.text"
```

## CLI arguments

- `--pdf`: input PDF path (optional)
- `--output`: output Excel path (default: `data/output/Output.xlsx`)
- `--prompt`: prompt file path (default: `prompts/prompt.text`)

## Output format

The generated workbook contains sheet `Output` with columns:

- `#`
- `Key`
- `Value`
- `Comments`

## Notes

- Groq is the primary LLM provider.
- If LLM extraction fails or is unavailable, regex fallback is used.
- Name rows are validated/enriched so `Full Name`, `First Name`, and `Last Name` are preserved when detectable.

## Troubleshooting

- `No PDF files found in data/input`:
	Add at least one PDF to `data/input/` or pass `--pdf`.

- `GROQ_API_KEY` not set:
	Add it to `.env`; otherwise extraction may fall back to regex mode.

- Output does not reflect expected file:
	Use `--pdf` to force the exact document path.