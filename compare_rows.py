import csv
a = {r["case_id"]: r for r in csv.DictReader(open("output.csv", newline="", encoding="utf-8"))}
b = {r["case_id"]: r for r in csv.DictReader(open("output_fixed.csv", newline="", encoding="utf-8"))}
d = [c for c in a if a[c] != b[c]]
s = [c for c in a if a[c]["deletion_status"] != b[c]["deletion_status"]]
print("rows:", len(a), len(b), "| differing rows:", d, "| status changes:", s)
