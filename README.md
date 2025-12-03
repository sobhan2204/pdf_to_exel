# AI Document Structurer

A small tool to convert an unstructured PDF into a structured Excel file (key, value, comments).

## Usage

- **Purpose:** extract all key:value pairs from a PDF, preserve original wording, add contextual comments, and save results to Excel.
- **Input:** place the PDF in `data/input/` (e.g., `Data Input.pdf`).
- **Run:** execute the pipeline (`run src/main.py` using your Python interpreter).
- **Output:** results saved to `data/output/Output.xlsx`.

## Notes

- **Gemini API:** optional. Add `GEMINI_API_KEY` to `.env` to enable Gemini; otherwise the tool uses a regex fallback.
- Requires Python 3.8+. Install project dependencies listed in `requirements.txt`.

That's it — place a PDF, run the pipeline, check `data/output/` for `Output.xlsx`.