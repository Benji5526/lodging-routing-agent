# 숙박 취소·환급 안내 챗봇

숙박 예약을 취소할 때 얼마를 돌려받는지 묻는 문의를 **분류하고 → 근거 문서에서 필요한 부분만 조회하고 → 근거로만 답하고 → 수치를 검증**하는
챗봇입니다. 문서에 없는 내용은 지어내지 않고 **되묻거나 상담원 확인으로 넘깁니다.**
근거 문서는 공정위 고시 「소비자분쟁해결기준」(제2025-14호, 2025.12.18 시행)의 숙박업·휴양콘도·국내여행 부분입니다.

설계 판단과 측정 결과는 [REPORT.md](REPORT.md), 실험 기록은 [EXPERIMENTS.md](EXPERIMENTS.md)에 있습니다.

![데모 화면](assets/demo_answer.jpg)

## 결과 요약

| 지표 (최종 설정, 재측정) | 평가용 22건 | 보류 30건 |
| --- | --- | --- |
| 분류 정확도 | 100% | 96.7% |
| ① 도구 호출 적절성 | 95.5% | 90.0% |
| ② 답변 적절성 | 100% | 96.7% |
| 둘 다 통과 | 95.5% | 90.0% |

**읽는 법**: 평가용 22건은 개선 실험 중에 반복해서 보고 규칙을 고쳤으므로 개발용입니다. 튜닝 중에 보지 않은 보류 30건에서
기준선(둘 다 통과 83~87%) 대비 개선은 3~7%p로 작고 확정적이지 않습니다. 자세한 내용과 한계는 REPORT.md 4장.

## 처리 흐름

```
고객 문의 → route(카테고리 판정) → gate(범위 밖·확신 낮음이면 넘기기)
          → answer(카테고리별 조회 도구로 근거 조회 후 답변 / 되묻기) → guard(답변 속 N% 가 근거에 있는가) → 끝
```

카테고리: 일반 취소·환급 / 천재지변·감염병·광고 / 휴양콘도 / 국내여행 패키지 / 범위 밖.
구조도(Mermaid)와 State 표는 REPORT.md 5장에 있습니다.

## 빠른 시작

필요한 것: Python 3.10 이상(3.12에서 확인), OpenAI API 키.

```bash
git clone <이 저장소 주소>
cd lodging-routing-agent
python -m venv .venv
```

가상환경을 켭니다.

```bash
# macOS / Linux / Git Bash
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
pip install -r requirements.txt
cp .env.example .env     # 그리고 OPENAI_API_KEY 를 채우세요
```

환경변수로 불러옵니다.

```bash
# macOS / Linux / Git Bash
set -a; . ./.env; set +a
```

```powershell
# Windows PowerShell
$env:OPENAI_API_KEY="sk-..."
```

한 문의를 터미널에서 돌려 봅니다.

```bash
python agent.py "성수기 금요일 숙박을 일주일 전에 제가 취소하려는데 얼마나 공제돼요?"
```

### 데모 화면

```bash
streamlit run app.py --server.address localhost
```

- 답변과 함께 분류, 호출한 도구와 인자, 검증 결과, 근거로 쓴 문서 부분을 보여 줍니다.
- API 키는 환경변수나 왼쪽 입력칸으로 받고 저장하지 않습니다.
- **`--server.address localhost` 를 빼지 마세요.** 기본값은 모든 네트워크 주소에 열려서, 환경변수의 키로 외부에서 접속해 쓸 수 있게 됩니다.

### 평가 재현

```bash
python scripts/validate_goldenset.py        # 평가셋 구조 검사 (API 호출 없음)
python evaluate.py                          # 채점기 자기 검증 + 평가용 22건
python evaluate.py --split holdout --skip-check   # 보류 30건
python evaluate.py --only R-03,C-04 --skip-check  # 평가용 중 특정 문항만
```

- 평가는 문항마다 파이프라인과 채점기를 호출합니다. 22건에 3~4분, 호출 100건 안팎이 듭니다.
- 결과는 LLM 호출이라 실행마다 조금씩 다릅니다. 결과 원본은 `runs/` 에 저장됩니다.
- 요청 한도 오류가 나면 `config.py` 의 `WORKERS` 를 낮추세요.
- 모델은 환경변수 `ROUTER_MODEL`, `ANSWER_MODEL`, `JUDGE_MODEL` 로 바꿉니다(기본값은 `config.py`).
  `agent.py` 의 답변 모델은 `reasoning_effort="none"` 으로 만들어서, 이 인자를 지원하지 않는 모델을 쓰면 오류가 납니다.
  그때는 `agent.py` 의 해당 인자를 지우세요.

## 파일 구성

| 파일 | 내용 |
| --- | --- |
| `docs/lodging_dispute_standard.md` | 근거 문서 (고시 표를 마크다운으로 옮김) |
| `data/goldenset.json` | 평가셋 62건: 문항, 기대 행동·도구, 필수 사실, 금지 사항, 모범 답안 |
| `config.py` | 모델, 임계값, 동시 호출 수 |
| `prompts.py` | 분류 지침, 답변 규칙, 넘기기 규칙 (예시는 `fewshot` 10건에서만) |
| `context.py` | 문서를 장·절로 쪼개고 카테고리별 근거를 조립 |
| `tools.py` | 조회 도구 4개와 `handoff` |
| `guard.py` | 답변 속 `N%` 의 출처 검증 |
| `agent.py` | LangGraph 파이프라인 |
| `evaluate.py` | 두 지표 측정, 채점기 자기 검증 |
| `app.py` | Streamlit 데모 |
| `scripts/validate_goldenset.py` | 평가셋 구조 검사 |
| `REPORT.md`, `EXPERIMENTS.md`, `PLAN.md` | 보고서, 실험 기록, 초기 설계 |
| `_versions/` | 실험마다 백업한 `prompts.py`, `tools.py`, `agent.py` |
| `runs/` | 평가 결과 원본(`*.json`)과 로그(`logs/`) |
| `assets/` | 데모 화면 캡처 |

### `runs/logs/` 파일 이름

| 이름 | 무엇을 잰 것 |
| --- | --- |
| `runs_base*` | 기준선, 평가용 22건 |
| `runs_exp1_*`, `runs_exp2_*`, `runs_exp3_*` | 실험 1~3, 평가용 22건 |
| `runs_gate_eval_*`, `runs_gate_new_*`, `runs_gate_old_*` | 실험 4(게이트, 철회) — 평가용 / 새 보류 H-21~H-30 / 이전 보류 H-01~H-20 |
| `runs_hold_base_*`, `runs_hold_cur_*` | 보류 1차(H-01~H-10): 기준선 / 현재(실험 3) |
| `runs_hold2_base_*`, `runs_hold2_cur_*` | 보류 2차(H-11~H-20). `runs_hold2_refcheck.txt` 는 모범 답안 합격 확인 |
| `runs_hold3_base_*`, `runs_hold3_pre_*` | 새 보류(H-21~H-30): 기준선 / 게이트 이전(최종 설정) |
| `runs_final_eval.txt`, `runs_final_holdout.txt` | 최종 재측정 (평가용 22건 + 채점기 검증 / 보류 30건) |

## 근거 문서와 면책

- 근거는 공정거래위원회고시 「소비자분쟁해결기준」 [별표 2]의 숙박업, 휴양콘도미니엄업, 국내여행 항목입니다
  (제2025-14호, 2025.12.18 시행). 환급률 표는 원본 PDF 화면과 쪽마다 대조해 옮겼습니다.
- 소비자분쟁해결기준은 분쟁 해결의 기준이며 법률 자문이 아닙니다. 사업자의 약관과 다를 수 있고, 이 챗봇은 문서에 없는 내용을 답하지 않습니다.
- 수업에서 제공받은 노드 소스·데이터는 이 저장소에 포함되어 있지 않습니다. 코드와 평가셋은 직접 작성했습니다.
