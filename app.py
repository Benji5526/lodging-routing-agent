"""숙박 취소·환급 안내 챗봇 데모.   streamlit run app.py

답변과 함께 분류, 행동(답변·되묻기·상담원 연결), 호출한 도구와 인자, 근거로 쓴 문서 부분, 검증 결과를 보여 준다.
API 키는 환경변수(OPENAI_API_KEY)나 왼쪽 입력칸으로 받고, 파일에 저장하지 않는다.
"""
import os

import streamlit as st

st.set_page_config(page_title="숙박 취소·환급 안내", page_icon=None, layout="wide")

EXAMPLES = [
    "비수기 평일 숙박인데 이틀 전에 취소하면 환불이 어떻게 되나요?",
    "7일 전에 취소하면 몇 퍼센트 돌려받아요?",
    "성수기 금요일 숙박을 일주일 전에 제가 취소하려는데 얼마나 공제돼요?",
    "태풍 경보 때문에 비행기가 결항돼서 숙소에 못 가게 됐어요. 당일 취소하면 환불되나요?",
    "휴양 콘도를 성수기 주말에 예약했는데 취소하면 몇 퍼센트가 공제되나요?",
    "숙박이 포함된 국내 패키지를 3일 전에 제가 취소하면 위약금이 있나요?",
    "환불을 신청하면 며칠 만에 입금되나요?",
]
ACTION_LABEL = {
    "ANSWER": ("답변", "green"),
    "ASK": ("되묻기", "blue"),
    "HANDOFF": ("상담원 연결", "orange"),
}
CATEGORY_LABEL = {
    "REFUND_RATE": "일반 취소·환급", "SPECIAL_CASE": "천재지변·감염병·광고",
    "CONDO": "휴양콘도", "PACKAGE": "국내여행 패키지", "OUT_OF_SCOPE": "범위 밖",
}

with st.sidebar:
    st.header("설정")
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        key = st.text_input("OpenAI API 키", type="password",
                            help="이 세션에서만 쓰고 저장하지 않습니다.")
        if key:
            os.environ["OPENAI_API_KEY"] = key
    else:
        st.caption("환경변수의 API 키를 사용합니다.")
    st.divider()
    st.subheader("이 챗봇이 다루는 것")
    st.markdown(
        "- 숙박 예약 취소 시 환급·공제·배상 비율\n"
        "- 천재지변, 1급 감염병, 허위·과장 광고\n"
        "- 휴양콘도미니엄 (계약 불일치, 이용 지연)\n"
        "- 숙박이 포함된 국내여행의 취소")
    st.caption("근거 문서: 공정위 고시 「소비자분쟁해결기준」(제2025-14호, 2025.12.18 시행) 별표 2의 "
               "숙박업·휴양콘도·국내여행. 분쟁 해결의 기준이며 법률 자문이 아닙니다. "
               "문서에 없는 내용은 답하지 않고 상담원 확인으로 넘깁니다.")
    st.divider()
    st.subheader("예시 문의")
    for i, ex in enumerate(EXAMPLES):
        if st.button(ex, key=f"ex{i}", use_container_width=True):
            st.session_state["pending"] = ex

st.title("숙박 취소·환급 안내")
st.caption("한 번에 한 문의씩 처리합니다(이전 대화를 기억하지 않습니다).")

if "history" not in st.session_state:
    st.session_state["history"] = []


def show_result(r):
    label, color = ACTION_LABEL.get(r["action"], (r["action"], "gray"))
    st.markdown(f":{color}-badge[{label}]")
    st.write(r["answer"])
    with st.expander("처리 과정 보기", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**① 분류**")
            st.write(f"{CATEGORY_LABEL.get(r['category'], r['category'])}")
            st.caption(f"확신도 {r['confidence']:.2f} · {r.get('route_reason', '')}")
        with c2:
            st.markdown("**② 호출한 도구**")
            args = r.get("tool_args") or []
            if args:
                for t in args:
                    shown = {k: v for k, v in t["args"].items() if v is not None}
                    st.code(f"{t['tool']}({', '.join(f'{k}={v!r}' for k, v in shown.items())})",
                            language="python", wrap_lines=True)
            if "handoff" in r["tools_called"]:
                st.code("handoff", language="python")
            if not r["tools_called"]:
                st.caption("호출한 도구 없음 (되묻기)")
        with c3:
            st.markdown("**③ 검증**")
            g = r.get("guard")
            if g is None:
                st.caption("해당 없음 (조회 없이 처리)")
            elif g["ok"]:
                st.success("통과")
                st.caption(f"답변 속 비율: {g['percents_in_answer'] or '없음'}")
            else:
                st.error(f"근거 문서에 없는 비율: {g['unsupported']}%")
    sections = r.get("sections") or []
    if sections:
        with st.expander(f"근거로 쓴 문서 부분 ({len(sections)}곳)"):
            for s in sections:
                st.markdown(f"- {s}")
            st.divider()
            st.markdown(r.get("evidence", ""))


for turn in st.session_state["history"]:
    with st.chat_message("user"):
        st.write(turn["question"])
    with st.chat_message("assistant"):
        show_result(turn["result"])

question = st.chat_input("숙박 예약 취소·환급에 대해 물어보세요") or st.session_state.pop("pending", None)
if question:
    if not os.environ.get("OPENAI_API_KEY"):
        st.warning("왼쪽에 OpenAI API 키를 입력해 주세요.")
        st.stop()
    from agent import run     # 키를 받은 뒤에 불러온다

    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        with st.spinner("근거 문서를 확인하는 중..."):
            try:
                result = run(question)
            except Exception as e:                  # 키 오류, 요청 한도 등을 화면에 그대로 알린다
                st.error(f"처리 중 오류가 났습니다: {type(e).__name__}: {str(e)[:300]}")
                st.stop()
        show_result(result)
    st.session_state["history"].append({"question": question, "result": result})
