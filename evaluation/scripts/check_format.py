import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    lines = [json.loads(l) for l in f if l.strip()]
print(f"Total records: {len(lines)}")
for i, r in enumerate(lines[:3]):
    ge = r.get("gold_entities", [])
    gf = r.get("gold_files", [])
    print(f"\n--- Record {i}: {r.get('question_id')} ---")
    print(f"  gold_entities type: {type(ge).__name__}, len={len(ge) if isinstance(ge, list) else 'N/A'}")
    if isinstance(ge, list) and len(ge) > 0:
        print(f"  gold_entities[0] type: {type(ge[0]).__name__}")
        print(f"  gold_entities[0]: {json.dumps(ge[0], ensure_ascii=False)[:200]}")
    print(f"  gold_files type: {type(gf).__name__}, len={len(gf) if isinstance(gf, list) else 'N/A'}")
    if isinstance(gf, list) and len(gf) > 0:
        print(f"  gold_files[0] type: {type(gf[0]).__name__}")
        print(f"  gold_files[0]: {json.dumps(gf[0], ensure_ascii=False)[:200]}")
