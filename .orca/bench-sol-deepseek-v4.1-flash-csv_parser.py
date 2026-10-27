import csv

class CSVParser:
    def parse(self, path):
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = None
            result = []

            for row in reader:
                if not row or all(cell == "" for cell in row):
                    continue

                if header is None:
                    header = row
                    continue

                result.append(dict(zip(header, row)))

            return result
