"""근거 조회 도구. 카테고리마다 하나씩이고, 문서의 해당 장만 돌려준다.

docstring 첫 줄이 모델이 읽는 도구 설명이다. 선택 인자는 Optional 로 적는다
(모델이 '모름'의 뜻으로 None 을 보냈을 때 스키마 검증에 걸리지 않게).
"""
from typing import Optional

from langchain.tools import tool

import context

HANDOFF_MESSAGE = "정확한 확인을 위해 상담원에게 연결해 드리겠습니다."


@tool
def lookup_refund_table(season: Optional[str] = None, day_type: Optional[str] = None) -> dict:
    """숙박 예약 취소 시 환급·공제·배상 기준표를 조회한다. 숙박일이 성수기/비수기인지(season),
    주중/주말인지(day_type)를 알면 값을 넘기고, 모르면 비워 둔다. season 은 '성수기' 또는 '비수기',
    day_type 은 '주중' 또는 '주말'이다."""
    text, sections = context.refund_evidence(season, day_type)
    return {"evidence": text, "sections": sections}


@tool
def lookup_special_cases() -> dict:
    """천재지변·기후변화, 1급 감염병, 거짓·과장 광고로 인한 숙박 계약 취소·변경 기준을 조회한다."""
    text, sections = context.build_evidence("2")
    return {"evidence": text, "sections": sections}


@tool
def lookup_condo() -> dict:
    """휴양콘도미니엄의 계약 불일치, 이용 지연 보상, 부당 이용료 기준을 조회한다."""
    text, sections = context.build_evidence("3")
    return {"evidence": text, "sections": sections}


@tool
def lookup_package() -> dict:
    """숙박이 포함된 국내여행(당일여행·숙박여행)의 취소, 인원 미달, 여행 중 피해 기준을 조회한다."""
    text, sections = context.build_evidence("4")
    return {"evidence": text, "sections": sections}


@tool
def handoff(reason: str) -> dict:
    """문서에 근거가 없거나 이 안내의 범위 밖이라 확답할 수 없을 때 상담원 확인으로 넘긴다.
    reason 에 넘기는 이유를 한 문장으로 적는다."""
    return {"handoff": True, "reason": reason, "message": HANDOFF_MESSAGE}


LOOKUP_BY_CATEGORY = {
    "REFUND_RATE": lookup_refund_table,
    "SPECIAL_CASE": lookup_special_cases,
    "CONDO": lookup_condo,
    "PACKAGE": lookup_package,
}
TOOLS = {t.name: t for t in
         [lookup_refund_table, lookup_special_cases, lookup_condo, lookup_package, handoff]}
