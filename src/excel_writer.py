import datetime
import re
from pathlib import Path

import pandas as pd


def _to_excel_value(value):
    """Convert plain strings to richer Excel-friendly values where safe."""
    if value is None:
        return None
    if isinstance(value, (int, float, datetime.date, datetime.datetime)):
        return value

    text = str(value).strip()
    if not text:
        return None

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return datetime.datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return text

    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    if re.fullmatch(r"[\d,]+", text):
        return int(text.replace(",", ""))

    if re.fullmatch(r"\d+(?:\.\d+)?%", text):
        return float(text[:-1]) / 100

    if re.fullmatch(r"\d+\.\d+", text):
        return float(text)

    return text


def write_to_excel(data: list, output_path: str = "data/output/Output.xlsx"):
    """
    Write structured data to Excel file.
    
    Args:
        data: List of dictionaries with keys: key, value, comments
        output_path: Path where Excel file will be saved
    """
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for idx, item in enumerate(data, start=1):
        key = item.get("key") if isinstance(item, dict) else None
        value = item.get("value") if isinstance(item, dict) else None
        comments = item.get("comments") if isinstance(item, dict) else None

        rows.append(
            {
                "#": idx,
                "Key": str(key).strip() if key is not None else "",
                "Value": _to_excel_value(value),
                "Comments": str(comments).strip() if comments is not None else None,
            }
        )

    df = pd.DataFrame(rows, columns=["#", "Key", "Value", "Comments"])

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        # Keep the first row blank so header appears on row 2 like the expected layout.
        df.to_excel(writer, index=False, sheet_name="Output", startrow=1)
        worksheet = writer.sheets["Output"]

        worksheet.freeze_panes = "C3"
        worksheet.column_dimensions["A"].width = 5
        worksheet.column_dimensions["B"].width = 36
        worksheet.column_dimensions["C"].width = 45
        worksheet.column_dimensions["D"].width = 90

        for header_cell in worksheet[2]:
            header_cell.font = header_cell.font.copy(bold=True)

    print(f" Excel file saved to: {output_path}")
    print(f" Total rows: {len(df)}")
