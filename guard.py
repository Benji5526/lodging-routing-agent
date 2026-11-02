"""답변 속 수치의 출처를 기계적으로 검사한다.

답변에 나온 'N%' 가 (1) 조회한 근거 문서나 (2) 고객 질문에 없으면 위반이다.
조회 없이 비율을 말했거나, 다른 구간의 표를 가져다 쓴 경우를 이 하나로 잡는다.
한계: 숫자가 아닌 오류(귀책 혼동, 구간 오판)는 못 잡는다.
"""
import re


def percents_in(text):
    return {int(m) for m in re.findall(r"(\d+)\s*%", text or "")}


def check(answer, evidence_text, question):
    found = percents_in(answer)
    allowed = percents_in(evidence_text) | percents_in(question)
    unsupported = sorted(found - allowed)
    return {"ok": not unsupported, "percents_in_answer": sorted(found),
            "unsupported": unsupported}
