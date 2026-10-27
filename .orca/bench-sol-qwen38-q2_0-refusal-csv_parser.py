import csv
from typing import List, Dict


class CSVParser:
    def parse(self, path: str) -> List[Dict[str, str]]:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = [row for row in reader if row]

            if not rows:
                return []

            header = rows[0]
            return [dict(zip(header, row)) for row in rows[1:]]
