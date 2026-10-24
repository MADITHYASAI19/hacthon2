import csv, json, glob, subprocess, sys
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
bad = set()
for r in rows("output.csv").values():
    for s in json.loads(r["steps_json"]):
        if s["resource_id"] not in text:
            bad.add((r["case_id"], s["resource_id"]))
print(f"FABRICATION: {len(bad)} resource_ids not found anywhere in dataset/")
print(sorted(bad)[:20])
