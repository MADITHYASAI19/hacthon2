import csv, json
def load(p): return {r["case_id"]: r for r in csv.DictReader(open(p, newline="", encoding="utf-8"))}
a, b = load("output.csv"), load("output_fixed2.csv")
req = {r["case_id"]: r["email"] for r in csv.DictReader(open("dataset/deletion_requests.csv", newline="", encoding="utf-8"))}
k = lambda s: (s["phase"], s["system_id"], s["resource_id"], s["operation"], s["state"], s["evidence_id"])
for c in sorted(a):
    if a[c] == b[c]: continue
    x = [k(s) for s in json.loads(a[c]["steps_json"])]
    y = [k(s) for s in json.loads(b[c]["steps_json"])]
    print(c, req[c], a[c]["deletion_status"], "->", b[c]["deletion_status"])
    for s in x:
        if s not in y: print("   REMOVED:", s)
    for s in y:
        if s not in x: print("   ADDED:  ", s)
