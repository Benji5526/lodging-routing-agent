"""두 지표를 잰다.   python evaluate.py [--only ID,ID] [--quiet] [--tag 이름]

① 도구 호출 적절성 — 실제로 호출한 도구 집합이 기대 도구와 정확히 같으면 1점.
   필요한 근거를 안 읽은 것, 관련 없는 근거를 훑은 것, 넘겨야 하는데 지어낸 것이 이 하나로 걸린다.
② 답변 적절성 — 반드시 담을 사실을 모두 담고, 말하면 안 되는 주장을 하나도 하지 않으면 1점.
   채점기(LLM)에게 표현이 아니라 사실을 보라고 지시한다.

평가용(eval) 문항만 잰다. 채점기는 먼저 모범 답안으로 자체 검증한다.
"""
import argparse
import json
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

from config import GOLDENSET_PATH, JUDGE_MODEL, ROOT, WORKERS


class Verdict(BaseModel):
    must_satisfied: list[bool] = Field(description="사실 목록 순서대로, 답변이 그 사실을 담았으면 true")
    forbid_violated: list[bool] = Field(description="금지 목록 순서대로, 답변이 그 주장을 했으면 true")
    comment: str = Field(description="판정 근거를 한 문장으로")


JUDGE_PROMPT = """\
너는 상담 답변 채점기다. 고객 문의에 대한 [답변]이 아래 기준을 지키는지 판정한다.

- [반드시 담을 사실] 각 항목: 표현이 달라도 의미가 같으면 담은 것(true). 빠졌거나 틀렸으면 false.
  숫자(비율, 일수)는 정확히 일치해야 한다.
- [말하면 안 되는 주장] 각 항목: 답변이 그 주장을 하거나 그렇게 읽히면 true. 하지 않았으면 false.
- 되묻기 답변은 사실 목록의 '되묻는다' 항목을 질문으로 실제로 던졌으면 담은 것으로 본다.
- 답변에 적힌 내용만 보고 판정한다. 답변이 맞을 것이라고 추측해서 채우지 않는다.
- 목록의 개수와 같은 길이로 순서대로 답한다.
"""

_judge = None


def judge(question, answer, must, forbid):
    global _judge
    if _judge is None:
        _judge = init_chat_model(JUDGE_MODEL, temperature=0, timeout=60, max_retries=2
                                 ).with_structured_output(Verdict)
    body = (f"[고객 문의]\n{question}\n\n[답변]\n{answer}\n\n"
            "[반드시 담을 사실]\n" + "\n".join(f"{i+1}. {m}" for i, m in enumerate(must)) +
            "\n\n[말하면 안 되는 주장]\n" + "\n".join(f"{i+1}. {f}" for i, f in enumerate(forbid)))
    v = _judge.invoke([("system", JUDGE_PROMPT), ("human", body)])
    if len(v.must_satisfied) != len(must) or len(v.forbid_violated) != len(forbid):
        return {"ok": False, "missing": ["(채점기 응답 길이 불일치)"], "violated": [], "comment": v.comment}
    missing = [m for m, s in zip(must, v.must_satisfied) if not s]
    violated = [f for f, x in zip(forbid, v.forbid_violated) if x]
    return {"ok": not missing and not violated, "missing": missing, "violated": violated,
            "comment": v.comment}


def tools_ok(expect_tools, called):
    exp, got = set(expect_tools), set(called)
    return exp == got, sorted(exp - got), sorted(got - exp)


def load_cases(split="eval", only=None):
    cases = json.loads(GOLDENSET_PATH.read_text(encoding="utf-8"))["cases"]
    cases = [c for c in cases if c["split"] == split]
    if only:
        cases = [c for c in cases if c["id"] in only]
    return cases


def pmap(fn, items):
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        return list(ex.map(fn, items))


def self_check(cases):
    """채점기 자체 검증. 모범 답안은 통과하고, 다른 문항의 답변은 떨어져야 한다."""
    pos = pmap(lambda c: judge(c["question"], c["reference"], c["expect"]["must"],
                               c["expect"]["forbid"]), cases)
    bad_pos = [c["id"] for c, r in zip(cases, pos) if not r["ok"]]
    # 같은 카테고리가 아닌 문항의 모범 답안을 가져와서 채점 → 통과하면 안 된다
    shifted = [cases[(i + 7) % len(cases)] for i in range(len(cases))]
    neg = pmap(lambda p: judge(p[0]["question"], p[1]["reference"], p[0]["expect"]["must"],
                               p[0]["expect"]["forbid"]), list(zip(cases, shifted)))
    bad_neg = [c["id"] for c, r in zip(cases, neg) if r["ok"]]
    print("── 채점기 자기 검증 ──")
    print(f"  모범 답안 {len(cases)}건 중 탈락 {len(bad_pos)}건 {bad_pos if bad_pos else '✅'}")
    print(f"  엉뚱한 답안 {len(cases)}건 중 합격 {len(bad_neg)}건 {bad_neg if bad_neg else '✅'}")
    return not bad_pos and not bad_neg


def main():
    from agent import run

    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="eval", choices=["eval", "holdout"], help="잴 문항 묶음")
    ap.add_argument("--only", help="쉼표로 구분한 문항 id")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--skip-check", action="store_true", help="채점기 자기 검증을 건너뛴다")
    ap.add_argument("--tag", default="run", help="runs/ 에 저장할 결과 파일 이름")
    args = ap.parse_args()

    cases = load_cases(args.split, only=set(args.only.split(",")) if args.only else None)
    if not args.skip_check:
        if not self_check(load_cases()):
            print("채점기가 기준을 못 넘었다. 채점기부터 고쳐야 한다.")
    print(f"\n── 평가 {len(cases)}건 ──")

    def one(c):
        out = run(c["question"])
        t_ok, miss, extra = tools_ok(c["expect"]["tools"], out["tools_called"])
        a = judge(c["question"], out["answer"], c["expect"]["must"], c["expect"]["forbid"])
        return {"id": c["id"], "category": c["category"], "question": c["question"],
                "expect_action": c["expect"]["action"], "action": out["action"],
                "route": out["category"], "expect_tools": c["expect"]["tools"],
                "tools_called": out["tools_called"], "tool_ok": t_ok, "tool_missing": miss,
                "tool_extra": extra, "answer_ok": a["ok"], "missing": a["missing"],
                "violated": a["violated"], "answer": out["answer"], "guard": out.get("guard")}

    rows = pmap(one, cases)
    n = len(rows)
    tool_rate = sum(r["tool_ok"] for r in rows) / n
    ans_rate = sum(r["answer_ok"] for r in rows) / n
    both = sum(r["tool_ok"] and r["answer_ok"] for r in rows) / n
    route_ok = sum((r["route"] == next(c["category"] for c in cases if c["id"] == r["id"]))
                   for r in rows) / n

    if not args.quiet:
        print("\n[카테고리별] 도구 / 답변 / 둘 다")
        for cat in sorted({r["category"] for r in rows}):
            rs = [r for r in rows if r["category"] == cat]
            print(f"  {cat:13} {sum(r['tool_ok'] for r in rs)}/{len(rs)}  "
                  f"{sum(r['answer_ok'] for r in rs)}/{len(rs)}  "
                  f"{sum(r['tool_ok'] and r['answer_ok'] for r in rs)}/{len(rs)}")
        print("\n[행동 판정] 행=기대, 열=실제")
        ct = Counter((r["expect_action"], r["action"]) for r in rows)
        for e in ("ANSWER", "ASK", "HANDOFF"):
            print(f"  {e:8}", {a: ct[(e, a)] for a in ("ANSWER", "ASK", "HANDOFF")})
        print("\n[틀린 문항] — 여기를 읽는 것이 개선의 출발점이다")
        for r in rows:
            if r["tool_ok"] and r["answer_ok"]:
                continue
            print(f"  {r['id']} (분류 {r['route']}, 기대 {r['expect_action']} → 실제 {r['action']})")
            if not r["tool_ok"]:
                print(f"     도구: 기대 {r['expect_tools']} 실제 {r['tools_called']}"
                      f" (빠짐 {r['tool_missing']}, 더 부름 {r['tool_extra']})")
            for m in r["missing"]:
                print(f"     빠진 사실: {m}")
            for v in r["violated"]:
                print(f"     금지 위반: {v}")
            print(f"     답변: {r['answer'][:110]}")

    print("\n══ 요약 ══")
    print(f"  분류 정확도          {100*route_ok:.0f}%")
    print(f"  ① 도구 호출 적절성   {100*tool_rate:.1f}% ({sum(r['tool_ok'] for r in rows)}/{n})")
    print(f"  ② 답변 적절성        {100*ans_rate:.1f}% ({sum(r['answer_ok'] for r in rows)}/{n})")
    print(f"  둘 다 통과           {100*both:.1f}% ({sum(r['tool_ok'] and r['answer_ok'] for r in rows)}/{n})")

    runs = ROOT / "runs"
    runs.mkdir(exist_ok=True)
    (runs / f"{args.tag}_{time.strftime('%m%d_%H%M%S')}.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
