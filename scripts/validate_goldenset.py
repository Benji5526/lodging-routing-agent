"""평가셋의 구조와 균형을 검사한다.  python scripts/validate_goldenset.py"""
import json
import sys
from collections import Counter
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "data" / "goldenset.json"
g = json.loads(PATH.read_text(encoding="utf-8"))
cases = g["cases"]
tools = set(g["tools"])
cats = set(g["categories"])
actions = set(g["design"]["actions"])
errors = []


def err(cid, msg):
    errors.append(f"{cid}: {msg}")


ids = [c["id"] for c in cases]
for dup in {i for i in ids if ids.count(i) > 1}:
    err(dup, "id 중복")

for c in cases:
    cid, e = c["id"], c["expect"]
    if c["split"] not in ("fewshot", "eval", "holdout"):
        err(cid, f"split 값 이상: {c['split']}")
    if c["category"] not in cats:
        err(cid, f"카테고리 이상: {c['category']}")
    if e["action"] not in actions:
        err(cid, f"action 이상: {e['action']}")
    bad = set(e["tools"]) - tools
    if bad:
        err(cid, f"없는 도구: {sorted(bad)}")
    if e["action"] == "ASK" and e["tools"]:
        err(cid, "ASK 인데 기대 도구가 있음")
    if e["action"] == "HANDOFF" and "handoff" not in e["tools"]:
        err(cid, "HANDOFF 인데 handoff 가 기대 도구에 없음")
    if e["action"] == "ANSWER" and (not e["tools"] or "handoff" in e["tools"]):
        err(cid, "ANSWER 인데 도구가 비었거나 handoff 가 있음")
    if not e["must"]:
        err(cid, "must 가 비었음")
    if not e["forbid"]:
        err(cid, "forbid 가 비었음")
    if not c.get("reference"):
        err(cid, "모범 답안(reference)이 비었음")
    if c["category"] == "OUT_OF_SCOPE" and e["tools"] != ["handoff"]:
        err(cid, "범위 밖은 기대 도구가 [handoff] 이어야 함")

# 예시용과 평가용 질문이 겹치면 안 된다
few = {c["question"] for c in cases if c["split"] == "fewshot"}
for c in cases:
    if c["split"] != "fewshot" and c["question"] in few:
        err(c["id"], "평가용 질문이 예시용과 같음")

print(f"전체 {len(cases)}건")
print("split × 카테고리")
table = Counter((c["split"], c["category"]) for c in cases)
for s in ("fewshot", "eval", "holdout"):
    print(f"  {s:8}", {k: table[(s, k)] for k in g["categories"]})
print("action × split")
ac = Counter((c["split"], c["expect"]["action"]) for c in cases)
for s in ("fewshot", "eval", "holdout"):
    print(f"  {s:8}", {a: ac[(s, a)] for a in sorted(actions)})
print("기대 도구 사용 횟수:", dict(Counter(t for c in cases for t in c["expect"]["tools"])))

if errors:
    print("\n오류")
    for m in errors:
        print(" -", m)
    sys.exit(1)
print("\n구조 검사 통과")
