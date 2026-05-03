# AI-Powered Resume Parser & Job Matcher

A Python-based intelligent pipeline that extracts unstructured text from PDF resumes, structures it into granular key-value pairs using Large Language Models (LLMs), and evaluates the candidate against a specific Job Description to generate a structured Excel report.

---

## Features

- **Intelligent PDF Extraction:** Reads raw text from candidate resumes or profile PDFs.
- **LLM-Powered Structuring:** Uses Groq (Llama 3) to break down unstructured text into atomic facts (e.g., Dates, Salaries, Education, Names).
- **Automated Job Evaluation:** Cross-references the candidate's profile against a provided Job Requirements text file.
- **Skill Categorization:** Automatically categorizes skills into:
  - **Matched Skills:** Required skills the candidate possesses (with extracted proficiency).
  - **Missing Skills:** Required skills the candidate lacks.
  - **Additional Skills:** Extra skills the candidate has that aren't explicitly required.
- **Efficacy Scoring:** Generates a percentage-based match score with reasoning.
- **Regex Fallback:** Robust rule-based fallback extraction if LLM API limits are reached.
- **Excel Export:** Outputs clean, formatted, and easily readable data into `.xlsx` spreadsheets.

---

## Project Structure

```text
├── data/
│   ├── input/
│   │   ├── candidate_resume.pdf       # Place input PDFs here
│   │   └── job_requirements.txt       # Define the job requirements here
│   └── output/
│       └── Output.xlsx                # Generated Excel reports
├── prompts/
│   └── prompt.text                    # Base instructions for the LLM
├── src/
│   ├── main.py                        # Entry point & CLI handler
│   ├── extract.py                     # PDF reading logic
│   ├── llm_structurer.py              # LLM chunking, prompting, and validation
│   └── excel_writer.py                # Pandas/OpenPyXL formatting logic
├── .env                               # API Keys (Not tracked in git)
└── README.md
```

---

## Setup

### Install Dependencies

Ensure you have Python 3.9+ installed. Install the required libraries:

```bash
pip install pandas openpyxl pdfplumber python-dotenv groq python-dateutil
```

### Set up Environment Variables

Create a `.env` file in the root directory and add your LLM API keys:

```env
GROQ_API_KEY=your_groq_api_key_here

# Optional: Specify models
GROQ_MODEL=llama-3.3-70b-versatile
```

---

## Usage

### 1. Prepare your inputs

Drop a candidate's resume PDF into `data/input/`.

Create a text file containing the job description (e.g., `data/input/my_custom_job.txt`).

### 2. Run the Pipeline

Execute the script from the root directory. You can specify the job description and output path via command-line arguments:

```bash
python src/main.py --job data/input/my_custom_job.txt --output data/output/Output_2.xlsx
```

---

## Command Line Arguments

- `--pdf`: Path to the specific PDF to process.  
  (If omitted, grabs the most recently modified PDF in `data/input/`).

- `--job`: Path to the job requirements text file.  
  (Defaults to `data/input/job_requirements.txt`).

- `--output`: Path where the Excel file should be saved.  
  (Defaults to `data/output/Output.xlsx`).

- `--prompt`: Path to the base LLM prompt.  
  (Defaults to `prompts/prompt.text`).

---

## Sample Output Format

```
#,Key,Value,Comments
1,Full Name,Vijay Kumar,Extracted from source.
2,Efficacy Score,85%,"Strong match for Data Engineer, but missing AWS certification."
3,Matched Skill,Python,Proficiency: 9 out of 10
4,Missing Skill,Docker,Required by job but not found in profile.
5,Additional Skill,Tableau,Proficiency: 8 out of 10
```

---

## Authors

Sobhan Panda  
Raghvendra Shaktawat  
Divyansh Sharma  
Divyansh Dutt Sharma