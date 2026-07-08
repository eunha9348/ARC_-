"""
core/prompt_builder.py
============================================================================
프롬프트 조립. 프로그램의 '두뇌'에 해당하며, 두 원칙을 프롬프트로 강제한다.

  제1원칙(환각 방지): 오직 '사용자 데이터'의 사실만 사용.
                      없는 사실은 만들지 않고, 필요하면 [보완필요] 로 표시.
  제2원칙(문체/맞춤법): 자소서 문체·맞춤법·문맥 자연스러움 확보.
  + 직무별 스타일/양식/HR 관점을 프롬프트에 주입.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .data_models import UserProfile, ReferenceExample
from .job_profiles import get_job_profile, get_region_style


# 시간 흐름(시계열)이 의미 있는 필드 — 표시 시 연도 기준 오름차순 정렬
TIME_ORDERED_FIELDS = {"education", "experiences", "projects", "activities", "awards"}


def _first_year(item: Any) -> int:
    """항목에서 첫 4자리 연도(1900~2099)를 추출. 없으면 정렬 뒤로 보낼 큰 값."""
    text = ""
    if isinstance(item, dict):
        text = " ".join(str(v) for v in item.values())
    else:
        text = str(item)
    m = re.search(r"(19|20)\d{2}", text)
    return int(m.group(0)) if m else 9999


def _chronological(items: list) -> list:
    """연도 기준 오름차순(과거→현재) 안정 정렬. 연도 없는 항목은 순서 유지."""
    return sorted(items, key=_first_year)


# --------------------------------------------------------------------------
#  사용자 데이터 → "사실 원장(fact sheet)" 문자열
# --------------------------------------------------------------------------
def build_fact_sheet(user: UserProfile) -> str:
    """
    UserProfile 을 '사실 원장' 텍스트로 직렬화.
    이 원장이 자소서 내용의 유일한 근거이며, 근거 검증 때도 이걸 기준으로 판단한다.

    경력/학력/프로젝트 등 시점이 있는 항목은 연도 기준(과거→현재)으로 정렬해
    제시함으로써, 생성 단계에서 시계열 역행을 예방한다. (원본 데이터는 불변)
    """
    data = user.to_dict()
    lines: list[str] = []
    label = {
        "name": "이름", "target_company": "지원회사", "target_job": "지원직무",
        "education": "학력", "experiences": "경력/인턴", "projects": "프로젝트",
        "skills": "보유역량/기술", "certifications": "자격증", "awards": "수상",
        "activities": "대외활동/동아리", "achievements": "정량성과",
        "strengths": "강점/성향", "motivation": "지원동기 메모",
        "career_goal": "입사후 포부", "extra_notes": "기타 메모",
    }
    for key, kor in label.items():
        val = data.get(key)
        if not val:
            continue
        if isinstance(val, list):
            items = _chronological(val) if key in TIME_ORDERED_FIELDS else val
            rendered = []
            for item in items:
                if isinstance(item, dict):
                    rendered.append(", ".join(f"{k}: {v}" for k, v in item.items()))
                else:
                    rendered.append(str(item))
            suffix = " (오래된 순 → 최신 순)" if key in TIME_ORDERED_FIELDS else ""
            lines.append(f"- {kor}{suffix}:")
            for r in rendered:
                lines.append(f"    · {r}")
        else:
            lines.append(f"- {kor}: {val}")
    return "\n".join(lines) if lines else "(제공된 사실 데이터 없음)"


# --------------------------------------------------------------------------
#  few-shot 스타일 예시 → 프롬프트 블록
# --------------------------------------------------------------------------
def build_style_examples_block(examples: list[ReferenceExample]) -> str:
    if not examples:
        return "(스타일 참고용 예시 없음 — 아래 직무 스타일 가이드만 따르세요.)"
    blocks = []
    for i, ex in enumerate(examples, 1):
        blocks.append(
            f"[스타일 예시 {i} | {ex.region} | {ex.job_key}]\n{ex.text}"
        )
    return "\n\n".join(blocks)


# --------------------------------------------------------------------------
#  공통 시스템 규칙(두 원칙)
# --------------------------------------------------------------------------
ANTI_HALLUCINATION_RULES = """\
[절대 규칙 — 반드시 지킬 것]
1) (제1원칙) 아래 '사용자 사실 원장'에 있는 내용만 근거로 사용한다.
   - 원장에 없는 회사명, 수치, 경험, 자격, 기술, 직함을 새로 만들어내지 말 것.
   - 어떤 사실도 추측/과장/윤색하지 말 것. 특히 숫자는 원장에 있는 값만 사용.
   - 내용을 더 채우고 싶어도 근거가 없으면 만들지 말고, 그 자리에
     "[보완필요: 무엇이 필요한지]" 형태로 표시할 것.
   - '스타일 예시'의 문장/사실을 절대 그대로 가져오지 말 것(문체만 참고).
2) (제2원칙) 한국어 맞춤법·띄어쓰기·문맥을 자연스럽게. 자소서 특유의
   담백하고 신뢰감 있는 문어체를 사용하고, 문장 간 논리가 매끄럽게 이어질 것.
3) 진부한 상투어(예: "저는 어릴 적부터", "귀사의 무궁한 발전")는 지양하고,
   구체적 사실과 성과 중심으로 서술할 것.
"""

WRITING_STYLE_RULES = """\
[서술 방식 규칙 — 나열 금지, 깊이 있게]
1) 경험 나열 금지: 문항과 회사에 가장 잘 맞는 경험 1개(많아야 2개)만 골라
   깊게 서술할 것. 여러 경험을 얕게 훑으며 나열하는 글은 실패작이다.
   - 선택한 경험은 무엇을(What), 언제(When), 어디서(Where), 어떻게(How)
     했는지, 그래서 어떤 결과와 성과가 나왔는지가 하나의 이야기로
     이어지도록 쓸 것.
2) 돌림노래 금지: 같은 강점·성과·표현을 말만 바꿔 반복하지 말 것.
   한 번 말한 내용은 다시 등장시키지 않는다.
3) 하나의 내러티브(중요): 문항 하나의 답변은 처음부터 끝까지 '한 편의 이야기'로
   읽혀야 한다. 문단이 따로 노는 조각들의 모음이 아니라, 앞 문단의 끝이 다음
   문단의 시작으로 자연스럽게 이어지는 하나의 흐름이어야 한다.
   - 도입에서 던진 핵심 메시지(주제)가 본문의 경험으로 증명되고, 마무리의
     포부로 다시 수렴하는 '기승전결'의 서사 곡선을 그릴 것.
   - 단순히 사실을 채우지 말고, 상황 속 긴장(문제)→선택과 행동→변화(결과)→
     그로부터 얻은 관점이 이어지도록 충분히 자세하고 밀도 있게 풀어 쓸 것.
   - 분량 제한이 허락하는 한 깊이 있게 서술하되, 곁가지로 늘리지 말고 하나의
     줄기를 더 선명하고 구체적으로 파고들 것.
4) 시간 흐름(시계열) 준수(중요): 경험·경력에 기간/연도/시점이 주어진 경우,
   서술은 반드시 시간 순서(과거→현재)로 흐르게 할 것.
   - 나중 시점의 경험을 먼저 이야기한 뒤 더 앞선 시점으로 되돌아가는(역행)
     구성 금지. 시점이 뒤섞여 독자가 시간 순서를 혼동하게 만들지 말 것.
   - 예: 2024년 인턴 경험을 서술한 뒤 2022년 동아리 경험으로 되돌아가지 말 것.
     성장의 서사는 앞선 경험이 뒤의 경험으로 이어지는 방향으로 배치할 것.
   - '이후', '그 경험을 바탕으로', '다음 해에는'처럼 시간의 전진을 드러내는
     연결로 성장 과정을 자연스럽게 이어갈 것.
5) 어미와 시점:
   - 어미는 '~했습니다/~입니다'체로 일관되게 통일할 것.
   - 단, 연속된 문장이 똑같은 어미로 끝나 단조로워지지 않도록 문장 구조와
     길이를 다양화할 것. (예: 명사절 활용, 쉼표로 절 연결, 문장 길이 변주)
   - '~하는 전문가이다', '~한 사람이다' 같은 제3자 관찰 시점의 단정 표현 금지.
     글 전체가 지원자 본인이 직접 말하는 1인칭 시점이어야 한다.
   - '~을 했습니다. ~을 했습니다. ~을 했습니다.' 식의 행동 보고 나열체 금지.
     행동 사이의 고민, 판단, 이유가 문장으로 드러나야 한다.
"""


# --------------------------------------------------------------------------
#  지원 회사 리서치 프롬프트 (Google 검색 그라운딩과 함께 사용)
# --------------------------------------------------------------------------
def build_company_research_prompt(company_name: str) -> str:
    return f"""\
당신은 기업 리서처입니다. Google 검색을 활용해 '{company_name}' 회사에 대해
아래 항목을 조사하고 간결하게 정리하세요. (한국 기업일 가능성이 높습니다)

1) 미션/비전/핵심가치 (공식 홈페이지·채용 페이지 표현 위주)
2) 인재상 (공개된 것이 있다면)
3) 최근 1~2년의 주력 사업/전략 방향
4) 조직문화 키워드

[규칙]
- 각 항목 2~3줄 이내로 간결하게.
- 검색으로 확인되지 않는 항목은 "확인 불가"로만 표시하고 절대 지어내지 말 것.
- 요약만 출력(사족 없이).
"""


def build_company_block(company_research: str) -> str:
    """생성 프롬프트에 넣을 '회사 가치 은은하게 반영' 지시 블록."""
    if not (company_research or "").strip():
        return "(회사 리서치 정보 없음 — 이 항목은 무시하고 직무 중심으로 작성)"
    return f"""{company_research}

[회사 가치 반영 규칙 — 반드시 지킬 것]
- 위 리서치의 회사 가치·지향점을 직접 인용하거나 나열하지 말 것.
  ("귀사의 핵심가치인 OO처럼", "귀사의 인재상에 부합하는" 등 노골적 언급 금지)
- 대신 ① 어떤 경험을 고를지, ② 그 경험에서 무엇을 강조할지, ③ 포부의 방향을
  회사가 가는 방향과 자연스럽게 맞닿게 하는 수준으로만 은은하게 스며들게 할 것.
- 읽는 인사담당자가 '이 지원자, 우리 회사를 제대로 이해하고 있네'라고
  느끼되, 회사 소개를 베꼈다는 인상은 받지 않아야 한다."""


# --------------------------------------------------------------------------
#  자소서 생성 프롬프트 — ★ 이 서비스의 핵심: '완성형 자소서'를 대신 써 준다
# --------------------------------------------------------------------------
def build_generation_prompt(
    user: UserProfile,
    job_key: str,
    region: str,
    question: str,
    examples: list[ReferenceExample],
    max_chars: int = 1000,
    tone: str = "",
    company_research: str = "",
) -> str:
    profile = get_job_profile(job_key)
    region_style = get_region_style(region)

    fact_sheet = build_fact_sheet(user)
    style_block = build_style_examples_block(examples)
    company_block = build_company_block(company_research)

    tone_line = tone.strip() or profile["tone"]
    length_line = (
        f"- 분량: 공백 포함 약 {max_chars}자. 제한의 90% 이상을 반드시 채워, 얕게 끝내지 말고"
        f" 하나의 경험을 깊게 파고들어 밀도 있게 서술할 것."
        if max_chars else "- 분량: 문항에 적절한 완결된 길이로, 충분히 자세하고 깊이 있게 작성."
    )
    question_line = question.strip() or "자유 형식의 자기소개서(핵심 강점과 지원동기 중심)"

    prompt = f"""\
당신은 지원자를 대신해 '그대로 제출해도 좋은 완성형 {region_style['label']}'를
집필하는 전문 자기소개서 작가입니다. 아래 사실 데이터를 재료로, 채용 담당자를
설득하는 완결된 글 한 편을 완성하는 것이 당신의 임무입니다.

{ANTI_HALLUCINATION_RULES}

{WRITING_STYLE_RULES}

[집필 지침 — 이 글은 '초안'이 아니라 '완성본'이다]
1) 두괄식: 첫 1~2문장에서 글의 핵심 메시지(강점과 직무 적합성)를 제시할 것.
   이 메시지가 글 전체를 관통하는 '하나의 주제'가 되어야 한다.
2) 본문은 위 서술 방식 규칙에 따라, 선택한 핵심 경험 하나를 What/When/Where/How
   와 결과·성과가 이어지는 완결된 이야기로 '깊고 자세하게' 풀어 쓸 것.
   - 상황의 배경과 문제의식 → 본인이 내린 판단과 구체적 행동 → 그 결과와
     수치 → 거기서 얻은 배움까지, 장면이 눈에 그려질 만큼 구체적으로 서술.
   - '사실'은 원장의 것만 사용하되, 문장·서사·연결·표현은 전문 작가 수준으로
     풍부하게 발전시킬 것. (사실 추가 금지 ≠ 건조한 나열)
   - 여러 경험을 언급해야 한다면, 시간 순서(과거→현재)로 배열해 성장의 흐름이
     한 방향으로 이어지게 하고, 앞 경험이 뒤 경험의 발판이 되도록 연결할 것.
3) 마지막 문단은 앞서 풀어낸 이야기가 자연스럽게 수렴하도록, 지원 회사·직무와의
   연결과 구체적인 기여 방향으로 마무리할 것. (도입의 주제와 호응시킬 것)
4) "[보완필요: ...]" 표시는 문항이 반드시 요구하는 내용인데 원장에 근거가 전혀
   없을 때만 최소한으로 사용할 것. 원장의 사실로 채울 수 있으면 사용하지 말 것.

[지원 직무 프로필]
- 직무: {profile['label']} (key={profile['key']})
- 이 직무에서 인사팀이 중점적으로 보는 것: {", ".join(profile['hr_focus'])}
- 핵심 역량 키워드: {", ".join(profile['competencies'])}
- 권장 문체/톤: {tone_line}
- 권장 구성 흐름: {" → ".join(profile['structure'])}
- 자연스럽게 녹이면 좋은 키워드(단, 사실과 무관하면 억지로 넣지 말 것):
  {", ".join(profile['keywords'])}

[지역(문화) 스타일 가이드]
{region_style['guidance']}

[지원 회사 리서치 — 은은하게만 반영할 것]
{company_block}

[사용자 사실 원장 — 지원자 사실의 유일한 출처]
{fact_sheet}

[문체 참고용 스타일 예시 — 내용 복붙 금지, 전개/톤만 참고]
{style_block}

[작성 요청]
- 자소서 문항: {question_line}
{length_line}
- 위 '권장 구성 흐름'을 기본 골격으로 하되, 문항 성격에 맞게 자연스럽게 조정.
- 한국형이라면 소제목(예: [데이터로 리스크를 읽는 힘])을 활용해도 좋음.

[출력 형식]
- 완성된 자소서 본문만 출력(머리말/설명/사족 없이).
"""
    return prompt


# --------------------------------------------------------------------------
#  최종 다듬기(polish) 프롬프트 — 제출 직전 완성도 끌어올리기 (제2원칙 강화)
# --------------------------------------------------------------------------
def build_polish_prompt(
    generated_text: str,
    user: UserProfile,
    max_chars: int = 1000,
) -> str:
    fact_sheet = build_fact_sheet(user)
    length_line = (
        f"- 분량: 공백 포함 약 {max_chars}자 수준을 유지할 것."
        if max_chars else "- 분량: 현재 수준을 유지할 것."
    )
    return f"""\
당신은 자기소개서 전문 교정가입니다. 아래 자기소개서를 '제출 직전 최종본'
수준으로 다듬으세요.

[사용자 사실 원장 — 유일한 사실 출처]
{fact_sheet}

[다듬을 자기소개서]
{generated_text}

[교정 지침]
- 새로운 사실을 추가하지 말 것(표현·흐름만 개선).
- 맞춤법·띄어쓰기·조사 오류, 어색한 번역투 교정.
- 어미 점검(중요):
  · '~했습니다/~입니다'체로 통일하되, 같은 어미가 3문장 이상 연속되면
    문장 구조를 바꿔 리듬을 살릴 것.
  · '~하는 전문가이다', '~한 사람이다' 같은 3인칭 관찰자식 표현이 남아
    있으면 1인칭 서술로 교정할 것.
- 반복 점검(중요): 같은 강점·성과·표현이 돌림노래처럼 반복되면 가장 강한
  한 곳만 남기고 정리할 것. 행동 보고 나열체('~했습니다'의 연속)는 행동
  사이의 고민과 판단이 드러나는 문장으로 연결할 것.
- 내러티브 점검(중요): 문단이 조각조각 따로 놀지 않고 처음-중간-끝이 하나의
  이야기로 이어지도록 문단 사이 연결을 매끄럽게 다듬을 것. 도입의 주제와
  마무리의 포부가 서로 호응하는지 확인할 것.
- 시간 흐름 점검(중요): 경험·경력에 시점(연도·기간)이 나올 경우 서술이
  과거→현재 순으로 흐르는지 확인하고, 나중 일을 말한 뒤 더 앞선 일로
  되돌아가는 시계열 역행이 있으면 순서를 바로잡을 것.
- 문단 연결과 문장 호흡을 매끄럽게, 두괄식 구조는 유지·강화.
- "[보완필요: ...]" 표시가 있다면 그대로 유지.
{length_line}
- 다듬어진 본문만 출력.
"""


# --------------------------------------------------------------------------
#  근거 검증(환각 탐지) 프롬프트
# --------------------------------------------------------------------------
def build_verification_prompt(
    generated_text: str,
    user: UserProfile,
    company_research: str = "",
) -> str:
    fact_sheet = build_fact_sheet(user)
    company_note = ""
    if (company_research or "").strip():
        company_note = f"""
[참고 — 회사 공개 정보(검색 리서치 결과)]
{company_research}
- 위 회사 정보의 범위 안에 있는 '회사에 대한' 서술은 문제 삼지 않는다.
  (단, 지원자 '본인의 경험/성과'는 반드시 사실 원장에 근거해야 한다)"""
    return f"""\
당신은 자기소개서 팩트체커입니다. 아래 '사용자 사실 원장'에 근거가 없는
문장/주장(지어낸 수치·경험·자격·기술 등)을 찾아내세요.

[사용자 사실 원장 — 지원자 사실의 유일한 출처]
{fact_sheet}
{company_note}

[검사할 자기소개서]
{generated_text}

[판정 규칙]
- 원장으로 뒷받침되지 않는 '지원자 본인에 대한' 구체적 사실 주장만 문제 삼는다.
- 일반적 다짐/포부/의지 표현(구체 사실 아님)이나 "[보완필요:...]" 표시는 문제 아님.
- 원장 내용을 자연스럽게 바꿔 쓴 것은 문제 아님(의미가 같으면 OK).

[출력 — 반드시 아래 JSON 만 출력]
{{
  "grounded": true 또는 false,
  "unsupported_claims": ["문제 문장 1", "문제 문장 2"],
  "notes": "간단한 총평(한 문장)"
}}
"""


# --------------------------------------------------------------------------
#  교정/재작성 프롬프트 (근거 없는 문장 제거)
# --------------------------------------------------------------------------
def build_correction_prompt(
    generated_text: str,
    user: UserProfile,
    unsupported_claims: list[str],
    company_research: str = "",
) -> str:
    fact_sheet = build_fact_sheet(user)
    claims = "\n".join(f"- {c}" for c in unsupported_claims) or "- (없음)"
    company_note = ""
    if (company_research or "").strip():
        company_note = f"""
[참고 — 회사 공개 정보(검색 리서치 결과), 이 범위의 회사 서술은 유지 가능]
{company_research}"""
    return f"""\
아래 자기소개서에서 '근거 없는 문장'들을 제거하거나, 사실 원장에 맞게
고쳐 쓰세요. 새로운 사실을 추가하지 말고, 문맥이 매끄럽도록 다듬으세요.

[사용자 사실 원장 — 지원자 사실의 유일한 출처]
{fact_sheet}
{company_note}

[제거/수정 대상(근거 없는 문장)]
{claims}

[원본 자기소개서]
{generated_text}

[요구사항]
- 근거 없는 사실은 삭제하거나, 원장에 있는 사실로 대체.
- 삭제로 빈 곳이 생기면 원장의 다른 사실로 자연스럽게 연결.
- 정 채울 근거가 없으면 "[보완필요: ...]"로 표시.
- 맞춤법·문맥·자소서 문체를 자연스럽게 유지.
- 완성된 본문만 출력.
"""


def safe_parse_json(text: str) -> dict[str, Any]:
    """
    모델이 준 응답에서 JSON 블록만 안전하게 파싱한다.
    코드펜스(```json ... ```)나 앞뒤 텍스트가 섞여 있어도 처리.
    """
    if not text:
        return {}
    t = text.strip()
    # 코드펜스 제거
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    # 가장 바깥 중괄호 범위 추출
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        t = t[start:end + 1]
    try:
        return json.loads(t)
    except Exception:
        return {}
