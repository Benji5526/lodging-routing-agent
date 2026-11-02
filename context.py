"""근거 문서를 장·절 단위로 쪼개고, 카테고리에 필요한 부분만 골라 근거로 조립한다.

문서 전체를 프롬프트에 넣지 않는 이유: 다른 구간의 표가 섞이면 비슷한 숫자를 잘못 골라 답하기 쉽다.
"""
import re

from config import DOC_PATH


def load_doc():
    """{'0': {'title':..., 'text':..., 'subs': {'1.1': (제목, 본문)}} ...} 형태로 돌려준다."""
    text = DOC_PATH.read_text(encoding="utf-8")
    chapters = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        head, _, body = block.partition("\n")
        num = re.match(r"(\d+)\.", head).group(1)
        parts = re.split(r"^### ", body, flags=re.M)
        subs = {}
        for p in parts[1:]:
            sh, _, sb = p.partition("\n")
            sid = re.match(r"(\d+\.\d+)", sh).group(1)
            subs[sid] = (sh.strip(), sb.strip())
        chapters[num] = {"title": head.strip(), "intro": parts[0].strip(), "subs": subs}
    return chapters


DOC = load_doc()

# 카테고리 → 근거 문서의 장. 이 표가 REPORT.md 의 매핑표와 같다.
CATEGORY_CHAPTERS = {
    "REFUND_RATE": ["1"],
    "SPECIAL_CASE": ["2"],
    "CONDO": ["3"],
    "PACKAGE": ["4"],
    "OUT_OF_SCOPE": [],
}

# 숙박업 환급 표 번호: (성수기/비수기, 주중/주말)
REFUND_TABLES = {("성수기", "주중"): "1.1", ("성수기", "주말"): "1.2",
                 ("비수기", "주중"): "1.3", ("비수기", "주말"): "1.4"}


def _chapter_text(num, only=None):
    ch = DOC[num]
    out, sections = [], []
    if ch["intro"]:
        out.append(f"[출처 {ch['title']}]\n{ch['intro']}")
        sections.append(ch["title"])
    for sid, (title, body) in ch["subs"].items():
        if only is None or sid in only:
            out.append(f"[출처 {title}]\n{body}")
            sections.append(title)
    return out, sections


def glossary():
    """0장(출처와 용어)은 모든 조회에 붙인다."""
    ch = DOC["0"]
    return f"[출처 {ch['title']}]\n{ch['intro']}"


def build_evidence(chapter, only=None):
    """장 하나(또는 그 안의 일부 절)를 근거 문자열로 만든다. (본문, 쓴 절 제목들)을 돌려준다."""
    parts, sections = _chapter_text(chapter, only)
    return "\n\n".join([glossary()] + parts), ["0. 이 문서에 대해"] + sections


def refund_evidence(season=None, day_type=None):
    """구간(성수기/비수기, 주중/주말)이 정해지면 그 표만, 모르면 1장 전체를 준다. 1.5 비고는 항상 붙는다."""
    seasons = [season] if season in ("성수기", "비수기") else ["성수기", "비수기"]
    days = [day_type] if day_type in ("주중", "주말") else ["주중", "주말"]
    want = {REFUND_TABLES[(s, d)] for s in seasons for d in days} | {"1.5"}
    return build_evidence("1", only=want)
