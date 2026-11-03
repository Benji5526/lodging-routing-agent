"""견고성 테스트. API 호출 없이 가짜 모델로 실패 경로를 확인한다.   python scripts/test_robustness.py

확인하는 것: 없는 도구 호출, 잘못된 인자, 도구 왕복 상한, 빈 입력, 너무 긴 입력.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent
from config import MAX_QUESTION_CHARS, MAX_TOOL_ROUNDS
from tools import HANDOFF_MESSAGE


class FakeResp:
    def __init__(self, content="", tool_calls=None):
        self.content, self.tool_calls = content, tool_calls or []


class FakeLLM:
    """미리 정한 응답을 차례로 돌려준다. 다 쓰면 마지막 응답을 반복한다."""

    def __init__(self, responses):
        self.responses, self.i = responses, 0

    def invoke(self, messages):
        r = self.responses[min(self.i, len(self.responses) - 1)]
        self.i += 1
        return r


def call(name, args, cid="c1"):
    return FakeResp(tool_calls=[{"name": name, "args": args, "id": cid}])


def run_answer(responses):
    agent._answer_llm = lambda category: FakeLLM(responses)
    return agent.node_answer({"question": "테스트 문의", "category": "REFUND_RATE", "attempts": 0})


def check(name, cond):
    print(("통과  " if cond else "실패  ") + name)
    if not cond:
        check.failed += 1


check.failed = 0

# 1. 없는 도구 이름 → 죽지 않고, 성공한 호출로 기록하지 않고, 다음 응답으로 이어 간다
r = run_answer([call("no_such_tool", {}), FakeResp("답변입니다")])
check("없는 도구 호출: 예외 없이 끝남", r["answer"] == "답변입니다")
check("없는 도구 호출: 도구 집합에 기록되지 않음", r["tools_called"] == [])

# 2. 잘못된 인자(타입 오류) → 죽지 않음
r = run_answer([call("lookup_refund_table", {"season": ["성수기"], "weekday": {"x": 1}}), FakeResp("다시 답변")])
check("잘못된 인자: 예외 없이 끝남", r["answer"] == "다시 답변")
check("잘못된 인자: 실패한 호출은 기록되지 않음", r["tools_called"] == [])

# 3. 정상 호출은 기록된다
r = run_answer([call("lookup_refund_table", {"season": "비수기", "weekday": "일요일"}), FakeResp("정상 답변")])
check("정상 호출: 기록되고 근거가 붙음", r["tools_called"] == ["lookup_refund_table"] and "1.3 비수기 주중" in r["sections"])
check("정상 호출: 행동이 ANSWER", r["action"] == "ANSWER")

# 4. 모델이 도구만 계속 부르는 폭주 → 왕복 상한에서 멈추고 지어내지 않고 넘김
r = run_answer([call("lookup_refund_table", {"season": "성수기"})])
check(f"폭주 방지: {MAX_TOOL_ROUNDS + 1}번째 왕복에서 멈추고 넘김",
      r["action"] == "HANDOFF" and r["answer"] == HANDOFF_MESSAGE)

# 5. 빈 입력과 공백 입력 → 모델을 부르지 않고 되묻는다
for q in ("", "   ", None):
    out = agent.run(q)
    check(f"입력 {q!r}: 되묻기, 모델 호출 없음", out["action"] == "ASK" and out["tools_called"] == [])

# 6. 너무 긴 입력은 앞부분만 쓴다
seen = {}


class FakeApp:
    def invoke(self, state):
        seen["len"] = len(state["question"])
        return {"question": state["question"], "category": "OUT_OF_SCOPE", "confidence": 1.0,
                "action": "HANDOFF", "tools_called": ["handoff"], "answer": "x"}


agent.agent_app = FakeApp()
agent.run("취소 " * 5000)
check(f"긴 입력: {MAX_QUESTION_CHARS}자로 자름", seen["len"] == MAX_QUESTION_CHARS)

print(f"\n실패 {check.failed}건")
sys.exit(1 if check.failed else 0)
