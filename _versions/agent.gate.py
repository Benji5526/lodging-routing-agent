"""판정 → 게이트 → 조회·답변 → 검증을 하나의 그래프로 잇는다. (LangGraph)

route → gate ─ HANDOFF ─────────────────────────────────────────────→ handoff → END
              └ ANSWER → answer → handoff_gate → guard ─ 통과 → END
                                                    ├ 위반(재시도 남음) → answer
                                                    └ 위반(재시도 없음) → handoff

handoff_gate: 질문의 핵심이 문서에 없어 확답하지 못한 답이면 넘기기로 처리한다.
넘길지 여부는 답변 모델의 도구 호출이 아니라 이 판정이 정한다(프롬프트 표현에 따라 흔들렸기 때문).
"""
import re
from typing import List, Optional, TypedDict

from langchain.chat_models import init_chat_model
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

import guard
from config import (ANSWER_MODEL, CATEGORIES, CONF_THRESHOLD, GUARD_RETRY, MAX_TOOL_ROUNDS,
                    ROUTER_MODEL)
from prompts import ANSWER_RULES, GATE_RULES, HANDOFF_RULES, ROUTE_GUIDE
from tools import HANDOFF_MESSAGE, LOOKUP_BY_CATEGORY, TOOLS


class AgentState(TypedDict, total=False):
    question: str
    category: str
    confidence: float
    route_reason: str
    action: str                 # ANSWER / ASK / HANDOFF
    tools_called: List[str]
    evidence: str               # 조회한 근거 본문(검증에 쓴다)
    sections: List[str]         # 근거로 쓴 문서 부분(화면에 보여 준다)
    answer: str
    guard: dict
    attempts: int
    feedback: Optional[str]


class CoreCheck(BaseModel):
    core_unanswered: bool = Field(
        description="질문의 핵심(비율, 금액, 기간, 가능 여부 등)에 대해 문서에 근거가 없다고 밝히고 확인처를 안내하는 답이면 true")
    reason: str = Field(description="판단 근거 한 문장")


class RouteDecision(BaseModel):
    category: str = Field(description=f"다음 중 하나: {', '.join(CATEGORIES)}")
    confidence: float = Field(ge=0.0, le=1.0, description="판단의 확신도. 애매하면 0.5 미만")
    reason: str = Field(description="그 카테고리로 판단한 근거 한 문장")


_router = None
_gate_llm = None
_answer_llms = {}


def _router_llm():
    global _router
    if _router is None:
        _router = init_chat_model(ROUTER_MODEL, temperature=0, timeout=60, max_retries=2
                                  ).with_structured_output(RouteDecision)
    return _router


def _answer_llm(category):
    if category not in _answer_llms:
        bound = [LOOKUP_BY_CATEGORY[category]]      # 넘기기는 모델이 아니라 handoff_gate 가 정한다
        # 이 등급의 모델은 추론 모드와 도구 호출을 함께 못 쓰는 경우가 있어 추론을 끈다.
        _answer_llms[category] = init_chat_model(
            ANSWER_MODEL, temperature=0, reasoning_effort="none", timeout=60, max_retries=2
        ).bind_tools(bound)
    return _answer_llms[category]


def node_route(state):
    d = _router_llm().invoke([("system", ROUTE_GUIDE), ("human", f"고객 문의: {state['question']}")])
    cat = d.category if d.category in CATEGORIES else "OUT_OF_SCOPE"
    return {"category": cat, "confidence": d.confidence, "route_reason": d.reason}


def gate(state):
    """모델이 한 분류를 정책으로 판정한다. 범위 밖이거나 확신이 낮으면 넘긴다."""
    if state["category"] == "OUT_OF_SCOPE" or state["confidence"] < CONF_THRESHOLD:
        return "handoff"
    return "answer"


def node_answer(state):
    cat = state["category"]
    sys_prompt = ANSWER_RULES + f"\n[현재 문의 카테고리: {cat}]"
    if state.get("feedback"):
        sys_prompt += f"\n[이전 답변의 문제] {state['feedback']}"
    messages = [("system", sys_prompt), ("human", state["question"])]
    llm = _answer_llm(cat)
    called, evidence, sections = [], [], []
    final = None
    for _ in range(MAX_TOOL_ROUNDS + 1):
        resp = llm.invoke(messages)
        messages.append(resp)
        if not resp.tool_calls:
            final = resp.content
            break
        for call in resp.tool_calls:
            name = call["name"]
            result = TOOLS[name].invoke(call["args"])
            called.append(name)
            if "evidence" in result:
                evidence.append(result["evidence"])
                sections.extend(result["sections"])
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "content": result.get("evidence") or str(result)})
    if final is None:                       # 왕복 상한에 걸리면 지어내지 않고 넘긴다
        return {"action": "HANDOFF", "tools_called": called + ["handoff"], "answer": HANDOFF_MESSAGE,
                "evidence": "\n".join(evidence), "sections": sections,
                "attempts": state.get("attempts", 0) + 1}
    if "handoff" in called:
        action = "HANDOFF"
    elif not any(t.startswith("lookup_") for t in called):
        action = "ASK"
    else:
        action = "ANSWER"
    return {"action": action, "tools_called": called, "answer": final,
            "evidence": "\n".join(evidence), "sections": sections,
            "attempts": state.get("attempts", 0) + 1}


def node_handoff_gate(state):
    """조회한 뒤의 답변이 질문의 핵심에 답했는지 본다. 핵심을 못 답했으면 넘기기로 처리한다."""
    global _gate_llm
    called = state.get("tools_called", [])
    if not any(t.startswith("lookup_") for t in called):      # 되묻기는 대상이 아니다
        return {}
    if _gate_llm is None:
        _gate_llm = init_chat_model(ROUTER_MODEL, temperature=0, timeout=60, max_retries=2
                                    ).with_structured_output(CoreCheck)
    c = _gate_llm.invoke([("system", GATE_RULES),
                          ("human", f"[고객 문의]\n{state['question']}\n\n[답변]\n{state['answer']}")])
    if not c.core_unanswered:
        return {}
    answer = state["answer"]
    if not re.search(r"상담원|사업자|여행사|약관|문의", answer):   # 확인처 안내가 빠졌으면 붙인다
        answer += " 정확한 확인은 예약하신 사업자나 상담원에게 문의해 주세요."
    return {"action": "HANDOFF", "tools_called": called + ["handoff"], "answer": answer}


def node_guard(state):
    g = guard.check(state["answer"], state.get("evidence", ""), state["question"])
    fb = None if g["ok"] else (
        f"답변에 근거 문서와 질문에 없는 비율 {g['unsupported']}%가 있다. 조회한 문서에 있는 값만 쓰고, "
        "문서에 없으면 단정하지 말고 되묻거나 handoff 로 넘겨라.")
    return {"guard": g, "feedback": fb}


def after_guard(state):
    if state["guard"]["ok"]:
        return END
    return "answer" if state.get("attempts", 0) <= GUARD_RETRY else "handoff"


_handoff_llm = None


def node_handoff(state):
    """범위 밖이거나 근거가 없을 때 지어내지 않고 넘긴다. 이유를 문의에 맞게 한두 문장으로 밝힌다."""
    global _handoff_llm
    if state.get("guard") and not state["guard"]["ok"]:      # 검증 위반이 재시도 후에도 남았다
        called = [t for t in state.get("tools_called", []) if t != "handoff"]
        return {"action": "HANDOFF", "tools_called": called + ["handoff"], "answer": HANDOFF_MESSAGE}
    if _handoff_llm is None:
        _handoff_llm = init_chat_model(ROUTER_MODEL, temperature=0, timeout=60, max_retries=2)
    msg = _handoff_llm.invoke([("system", HANDOFF_RULES),
                               ("human", f"고객 문의: {state['question']}")]).content
    return {"action": "HANDOFF", "tools_called": ["handoff"], "answer": msg}


def build_agent():
    g = StateGraph(AgentState)
    g.add_node("route", node_route)
    g.add_node("answer", node_answer)
    g.add_node("handoff_gate", node_handoff_gate)
    g.add_node("guard", node_guard)
    g.add_node("handoff", node_handoff)
    g.add_edge(START, "route")
    g.add_conditional_edges("route", gate, {"answer": "answer", "handoff": "handoff"})
    g.add_edge("answer", "handoff_gate")
    g.add_edge("handoff_gate", "guard")
    g.add_conditional_edges("guard", after_guard,
                            {"answer": "answer", "handoff": "handoff", END: END})
    g.add_edge("handoff", END)
    return g.compile()


agent_app = build_agent()


def run(question):
    """문의 한 줄을 파이프라인에 통과시킨다."""
    out = agent_app.invoke({"question": question, "attempts": 0})
    out.setdefault("tools_called", [])
    return out


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "비수기 평일 숙박인데 이틀 전에 취소하면 환불이 어떻게 되나요?"
    r = run(q)
    print("카테고리:", r["category"], f"(확신 {r['confidence']:.2f})")
    print("행동:", r["action"], "| 호출 도구:", r["tools_called"])
    print("근거:", r.get("sections"))
    print("검증:", r.get("guard"))
    print("답변:", r["answer"])
