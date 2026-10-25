import csv, json, glob, os, subprocess, sys
from pathlib import Path

def rows(p):
    return {r["case_id"]: r for r in csv.DictReader(open(p, encoding="utf-8", newline=""))}

if not Path("sample_out.csv").exists():
    subprocess.run(
        [
            sys.executable, "code/main.py", "--requests",
            "dataset/sample_deletion_requests.csv", "--out", "sample_out.csv", "--offline",
        ],
        check=True,
    )

# 1. Sample accuracy vs gold
g = rows("dataset/sample_output.csv")
p = rows("sample_out.csv")
st = sum(g[k]["deletion_status"] == p[k]["deletion_status"] for k in g)
ex = sum(json.loads(g[k]["steps_json"]) == json.loads(p[k]["steps_json"]) for k in g)
print(f"SAMPLE status {st}/{len(g)}   exact {ex}/{len(g)}   (before fixes: 32/32 and 13/32)")

# 2. Fabrication check on the full output
text = open("dataset/system_activity.csv", encoding="utf-8", errors="ignore").read()
for f in glob.glob("dataset/evidence/**/*", recursive=True):
    if f.endswith((".json", ".log", ".txt", ".sql")):
        text += open(f, encoding="utf-8", errors="ignore").read()
def media_enabled(name):
    return os.environ.get(name, os.environ.get("USE_MEDIA_EVIDENCE", "0")) == "1"

if media_enabled("USE_PDF_EVIDENCE") or media_enabled("USE_IMAGE_OCR"):
    from code.extract.doc_extract import extract_doc_evidence
    from code.extract.image_extract import extract_image_evidence
    from code.loader import parse_ts

    for evidence in csv.DictReader(open("dataset/evidence_files.csv", encoding="utf-8", newline="")):
        path = Path(evidence["file_path"])
        if path.suffix.lower() == ".pdf" and media_enabled("USE_PDF_EVIDENCE"):
            records = extract_doc_evidence(path, evidence["file_id"], parse_ts(evidence.get("captured_at", "")))
        elif path.suffix.lower() in {".png", ".jpg", ".jpeg"} and media_enabled("USE_IMAGE_OCR"):
            records = extract_image_evidence(path, evidence["file_id"], parse_ts(evidence.get("captured_at", "")))
        else:
            continue
        text += "\n".join(record.resource_id for record in records)
bad = set()
for r in rows("output.csv").values():
    for s in json.loads(r["steps_json"]):
        if s["resource_id"] not in text:
            bad.add((r["case_id"], s["resource_id"]))
print(f"FABRICATION: {len(bad)} resource_ids not found anywhere in dataset/")
print(sorted(bad)[:20])
