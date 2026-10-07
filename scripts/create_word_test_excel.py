"""Create sample Excel for Word invoice date testing."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sample_data" / "word_invoice_test.xlsx"

df = pd.DataFrame({"Invoice": [1, 2, 3, 4, 5]})
OUT.parent.mkdir(exist_ok=True)
df.to_excel(OUT, index=False)
print(f"Wrote {OUT}")
