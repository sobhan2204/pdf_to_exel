import pandas as pd
from pathlib import Path


def write_to_excel(data: list, output_path: str = "data/output/Output.xlsx"):
    """
    Write structured data to Excel file.
    
    Args:
        data: List of dictionaries with keys: key, value, comments
        output_path: Path where Excel file will be saved
    """
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(data)
    df = df[["key", "value", "comments"]]
    

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Structured Data')
        
        worksheet = writer.sheets['Structured Data']
        
        worksheet.column_dimensions['A'].width = 25
        worksheet.column_dimensions['B'].width = 40
        worksheet.column_dimensions['C'].width = 50
    
    print(f" Excel file saved to: {output_path}")
    print(f" Total rows: {len(df)}")
