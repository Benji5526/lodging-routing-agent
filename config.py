"""모델과 임계값을 한곳에 모았다. 환경변수로 바꿀 수 있다."""
import os
from pathlib import Path

ROOT = Path(__file__).parent
DOC_PATH = ROOT / "docs" / "lodging_dispute_standard.md"
GOLDENSET_PATH = ROOT / "data" / "goldenset.json"

ROUTER_MODEL = os.environ.get("ROUTER_MODEL", "gpt-5.6-luna")      # 분류: 출력이 짧다
ANSWER_MODEL = os.environ.get("ANSWER_MODEL", "gpt-5.6-terra")     # 도구 호출과 답변
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", ANSWER_MODEL)          # 채점기

CONF_THRESHOLD = 0.5       # 분류 확신도가 이보다 낮으면 넘긴다
MAX_TOOL_ROUNDS = 3        # 도구 호출 왕복 상한
MAX_QUESTION_CHARS = 1000  # 이보다 긴 입력은 앞부분만 쓴다
GUARD_RETRY = 1            # 검증 위반 시 다시 생성하는 횟수
WORKERS = 6                # 평가 시 동시 호출 수

CATEGORIES = ["REFUND_RATE", "SPECIAL_CASE", "CONDO", "PACKAGE", "OUT_OF_SCOPE"]
