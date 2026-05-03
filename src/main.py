import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.extract import extract_text_from_pdf
from src.llm_structurer import structure_text_with_llm
from src.excel_writer import write_to_excel


def resolve_pdf_path(pdf_path: str | None = None) -> str:
    if pdf_path:
        return pdf_path

    input_dir = Path("data/input")
    if not input_dir.exists():
        raise FileNotFoundError("Input directory not found: data/input")

    pdf_files = list(input_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError("No PDF files found in data/input")

    latest_pdf = max(pdf_files, key=lambda p: p.stat().st_mtime)
    return str(latest_pdf)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PDF to structured Excel pipeline")
    parser.add_argument(
        "--pdf",
        dest="pdf_path",
        default=None,
        help="Path to input PDF. If omitted, newest PDF from data/input is used.",
    )
    parser.add_argument(
        "--output",
        dest="output_path",
        default="data/output/Output.xlsx",
        help="Path for output Excel file.",
    )
    parser.add_argument(
        "--prompt",
        dest="prompt_path",
        default="prompts/prompt.text",
        help="Path to prompt instructions.",
    )
    parser.add_argument(
        "--job",
        dest="job_path",
        default="data/input/job_requirements.txt",
        help="Path to the job requirements text file.",
    )
    return parser.parse_args()


def main(pdf_path: str | None = None,
         output_path: str = "data/output/Output.xlsx",
         prompt_path: str = "prompts/prompt.text",
         job_path: str = "data/input/job_requirements.txt"):
    
    print("=" * 60)
    print(" DOCUMENTED :) ")
    print("=" * 60)
    
    try:
        selected_pdf_path = resolve_pdf_path(pdf_path)
        print(f" Input PDF selected: {selected_pdf_path}")

        # Load job requirements if provided
        job_desc = ""
        job_file = Path(job_path)
        if job_file.exists():
            job_desc = job_file.read_text(encoding="utf-8")
            print(f" Loaded job requirements from: {job_path}")
        else:
            print(f" Notice: No job requirements found at {job_path}. Proceeding with standard extraction.")

        print("\n Step 1: Extracting text from PDF...")
        raw_text = extract_text_from_pdf(selected_pdf_path)
        print(f" Extracted {len(raw_text)} characters")
        
        print("\n Step 2: Structuring text...")
        # Pass the job description to the structurer
        structured_data = structure_text_with_llm(raw_text, prompt_path, job_desc)
        
        print("\n Step 3: Writing to Excel...")
        write_to_excel(structured_data, output_path)
        
        print("\n" + "=" * 60)
        print("  Document Structuring Complete.")
        print("=" * 60)
        
    except FileNotFoundError as e:
        print(f"\n Error: {e}")
        print("Please put the input PDF file in data/input/ path or pass --pdf <path>")
        sys.exit(1)
    except Exception as e:
        print(f"\n Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    args = parse_args()
    main(
        pdf_path=args.pdf_path,
        output_path=args.output_path,
        prompt_path=args.prompt_path,
        job_path=args.job_path,
    )