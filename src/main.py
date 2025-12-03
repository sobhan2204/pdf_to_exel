import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.extract import extract_text_from_pdf
from src.llm_structurer import structure_text_with_llm
from src.excel_writer import write_to_excel


def main(pdf_path: str = "data/input/Data Input.pdf", 
         output_path: str = "data/output/Output.xlsx",
         prompt_path: str = "prompts/prompt.text"):
    """
    Main pipeline: PDF → Structured Data → Excel
    
    Args:
        pdf_path: Path to input PDF file
        output_path: Path for output Excel file
        prompt_path: Path to prompt instructions
    """
    print("=" * 60)
    print(" DOCUMENTED :) ")
    print("=" * 60)
    
    try:
        print("\n Step 1: Extracting text from PDF...")
        raw_text = extract_text_from_pdf(pdf_path)
        print(f" Extracted {len(raw_text)} characters")
        
        print("\n Step 2: Structuring text...")
        structured_data = structure_text_with_llm(raw_text, prompt_path)
        
        print("\n Step 3: Writing to Excel...")
        write_to_excel(structured_data, output_path)
        
        print("\n" + "=" * 60)
        print("  Document Structuring Complete.")
        print("=" * 60)
        
    except FileNotFoundError as e:
        print(f"\n Error: {e}")
        print("Please put the input PDF file in data/input/ path ")
        sys.exit(1)
    except Exception as e:
        print(f"\n Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
