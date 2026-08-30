"""
schema/export_schema.py
============================================================================
응답 스키마(analysis_result.ts) ↔ 실제 코드 출력의 일치 검사

스키마 문서를 손으로 관리하면 반드시 코드와 어긋난다. 실제로 v1.1 → v1.2 에서
후처리가 필드 8개를 추가하고 action_plan 구조를 바꿨지만, 프롬프트 템플릿의
JSON 예시는 그대로여서 한 파일 안에서 두 곳이 서로 다른 형태를 말하고 있었다.

이 스크립트는 career_individual 의 실제 후처리 파이프라인을 통과시킨 응답을
analysis_result.ts 와 대조해, 어긋나면 exit 1 로 실패한다.

검사 항목 4가지
  1. 인터페이스 필드 ↔ 실제 응답 키   (양방향 — 어느 쪽에만 있어도 검출)
  2. 중첩 객체 8종도 동일하게 대조
  3. 런타임 검증기의 REQUIRED_RESULT_KEYS ↔ AnalysisResult 인터페이스
     (파일 내부 정합성 — 둘이 어긋나면 검증기가 헛돈다)
  4. EXAMPLE_SUCCESS 가 실제 응답과 같은 형태인지 (예시 노후화 방지)

사용법:
  python schema/export_schema.py            # 검사만
  python schema/export_schema.py --write    # 검사 + EXAMPLE_SUCCESS 갱신
============================================================================
"""

from __future__ import annotations

import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_TS_PATH = os.path.join(_HERE, "analysis_result.ts")
sys.path.insert(0, _ROOT)

import career_individual as ci  # noqa: E402


# 프롬프트 템플릿이 모델에게 요구하는 형태를 그대로 채운 응답.
# (LLM 호출 없이 후처리 파이프라인만 실제로 통과시킨다)
_LLM_RESPONSE = {
    "status": "success",
    "item_name": "OO스타트업 데이터 분석 인턴",
    "item_type": "인턴십",
    "brief_summary": "5개월간 사용자 행동 로그를 분석해 리텐션 개선 지표를 도출한 인턴 경험",
    "star_format": {
        "title": "사용자 행동 로그 분석으로 리텐션 개선 지점 도출",
        "S": "월 활성 사용자가 정체된 상황에서 원인 파악이 필요했다",
        "T": "로그 데이터에서 이탈 구간을 찾아내는 과제를 맡았다",
        "A": "SQL로 퍼널 단계별 이탈률을 집계하고 코호트별로 비교했다",
        "R": "온보딩 3단계에서 이탈이 집중됨을 확인해 개선안이 채택되었다",
    },
    "star_note": None,
    "deep_analysis": {
        "career_value": "실데이터로 가설을 검증해본 경험은 신입 데이터 직군에서 변별력이 있다",
        "market_value": "SQL 기반 로그 분석 역량은 수요가 꾸준하나 지원자 수도 많아 희소성은 보통",
        "applicable_roles": ["데이터 분석가", "프로덕트 애널리스트", "그로스 마케터"],
    },
    "item_strengths": {
        "has_genuine_strengths": True,
        "one_line_strength_verdict": "가설 수립부터 검증까지 분석 사이클을 한 번 완주한 경험",
        "no_strength_reason": None,
        "summarized_strengths": ["퍼널 분석 실무 경험", "분석 결과가 실제 의사결정에 반영됨"],
        "strengths": [
            {
                "id": 1,
                "category": "성과_입증",
                "strength_level": "notable",
                "title": "개선안 채택",
                "analysis": "분석이 보고서로 끝나지 않고 실제 제품 변경으로 이어진 점이 핵심이다",
                "evidence": "온보딩 3단계 이탈 확인 후 개선안 채택",
                "career_impact": "분석의 실효성을 입증할 수 있어 면접에서 강한 근거가 된다",
                "leverage_action": "채택된 개선안의 이후 지표 변화를 수치로 확보하라",
                "showcase_example": "Before: 로그 분석 수행 → After: 퍼널 이탈 구간을 특정해 개선안 채택",
            }
        ],
        "strongest_asset": "분석 결과가 제품 의사결정으로 연결된 이력",
        "positioning_tip": "지표 정의 → 분석 → 의사결정 반영 순서로 서술하면 설득력이 올라간다",
    },
    "item_diagnosis": {
        "one_line_verdict": "경험의 흐름은 갖췄으나 성과를 뒷받침할 숫자가 전무하다",
        "limitations": ["개선 효과를 나타내는 수치가 없다", "5년 전 경험이라 최신성이 떨어진다"],
        "weaknesses": [
            {
                "id": 1,
                "category": "성과_불명확",
                "severity": "major",
                "title": "수치 부재",
                "diagnosis": "'개선안이 채택되었다'로 끝나 실제 효과 크기를 알 수 없다",
                "evidence": "입력 전체에 이탈률·전환율 수치가 하나도 없음",
                "impact": "면접에서 '얼마나 개선됐나' 질문에 답하지 못하면 신뢰가 떨어진다",
                "priority_action": "당시 대시보드나 보고 자료에서 개선 전후 수치를 복원하라",
                "improvement_example": "Before: 개선안 채택 → After: 온보딩 이탈률 32%→24%로 8%p 감소",
            }
        ],
        "missing_elements": ["개선 전후 지표 수치", "분석 대상 데이터 규모", "팀 구성과 본인 역할 비중"],
        "rewrite_suggestion": "문제 정의와 수치 결과를 앞뒤에 배치하고 분석 과정은 압축해 서술한다",
    },
    "synergy_recommendations": [
        {
            "priority": 1,
            "category": "자격증",
            "name": "SQLD",
            "reason": "실무에서 쓴 SQL 역량을 객관적으로 증명할 수 있다",
            "expected_effect": "경력 기술과 자격이 서로를 뒷받침해 신뢰도가 올라간다",
            "estimated_duration": "2개월",
        },
        {
            "priority": 2,
            "category": "프로젝트",
            "name": "공개 데이터 기반 리텐션 분석 포트폴리오",
            "reason": "5년 전 경험의 최신성 문제를 최근 산출물로 보완한다",
            "expected_effect": "현재도 분석이 가능하다는 점을 직접 보여줄 수 있다",
            "estimated_duration": "1개월",
        },
    ],
    "action_plan": {
        "단기": "당시 분석 지표를 복원해 이력서 문장에 수치를 넣는다",
        "중기": "SQLD를 취득하고 최근 데이터로 포트폴리오를 1건 만든다",
        "장기": "도메인을 정해 해당 산업의 지표 체계에 대한 전문성을 쌓는다",
    },
    "missing_info_warning": None,
}

_SAMPLE_INPUT = "2021.03~2021.08 OO스타트업 데이터 분석 인턴, 사용자 행동 로그 분석 담당"

# 인터페이스 이름 → 응답에서의 위치
_NESTED = {
    "StarFormat": "star_format",
    "DeepAnalysis": "deep_analysis",
    "ItemStrengths": "item_strengths",
    "ItemDiagnosis": "item_diagnosis",
    "ActionPlanWindow": None,          # action_plan.단기/중기/장기 에 개별 적용
    "TimeContext": "time_context",
    "TimeResolution": "input_time_resolution",
    "ValidationMeta": "validation",
}


def build_example() -> dict:
    """실제 후처리 파이프라인을 통과시킨 예시 응답 envelope."""
    tc = ci.TimeContext()
    time_facts = ci.extract_time_facts(_SAMPLE_INPUT, tc)
    result = ci.postprocess_result(json.loads(json.dumps(_LLM_RESPONSE)), tc, time_facts)
    result["embedding_dim"] = 3072

    payload = {k: v for k, v in result.items() if k not in ("status", "vector")}
    return {"status": "success", "vector": [0.0123, -0.0456, 0.0789], "result": payload}


# ── TypeScript 파싱 ────────────────────────────────────────
def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", src)


def _match_braces(src: str, start: int) -> int:
    """start 위치의 '{' 에 대응하는 '}' 인덱스를 반환."""
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("중괄호가 닫히지 않았습니다")


def parse_interfaces(src: str) -> dict[str, list[str]]:
    """export interface 의 필드명을 추출한다 (주석 제거 후)."""
    clean = _strip_comments(src)
    out: dict[str, list[str]] = {}
    for m in re.finditer(r"export\s+interface\s+(\w+)\s*\{", clean):
        name = m.group(1)
        body = clean[m.end() - 1: _match_braces(clean, m.end() - 1) + 1]
        out[name] = re.findall(r"^\s+([가-힣A-Za-z_][가-힣\w]*)\??\s*:", body, re.M)
    return out


def parse_required_keys_const(src: str) -> list[str]:
    """런타임 검증기의 REQUIRED_RESULT_KEYS 배열을 추출한다."""
    m = re.search(r"REQUIRED_RESULT_KEYS\s*=\s*\[(.*?)\]\s*as const", src, re.DOTALL)
    return re.findall(r'"([^"]+)"', m.group(1)) if m else []


def parse_example(src: str) -> tuple[dict, int, int] | None:
    """EXAMPLE_SUCCESS 리터럴을 파싱하고 위치를 함께 반환한다."""
    m = re.search(r"EXAMPLE_SUCCESS\s*:\s*AnalysisSuccess\s*=\s*", src)
    if not m:
        return None
    start = src.index("{", m.end())
    end = _match_braces(src, start)
    return json.loads(src[start:end + 1]), start, end + 1


# ── 검사 ──────────────────────────────────────────────────
def _diff(label: str, expected: set[str], actual: set[str]) -> list[str]:
    problems = []
    for missing in sorted(expected - actual):
        problems.append(f"스키마에는 있으나 실제 응답에 없음: {label}.{missing}")
    for extra in sorted(actual - expected):
        problems.append(f"실제 응답에 있으나 스키마에 없음: {label}.{extra}")
    return problems


def check(ts_src: str, example: dict) -> list[str]:
    problems: list[str] = []
    interfaces = parse_interfaces(ts_src)
    result = example["result"]

    if "AnalysisResult" not in interfaces:
        return ["analysis_result.ts 에서 AnalysisResult 인터페이스를 찾지 못했습니다"]

    # 1) 최상위 필드
    problems += _diff("result", set(interfaces["AnalysisResult"]), set(result.keys()))

    # 2) 중첩 객체
    for iface, key in _NESTED.items():
        if key is None or iface not in interfaces:
            continue
        value = result.get(key)
        if isinstance(value, dict):
            problems += _diff(key, set(interfaces[iface]), set(value.keys()))

    # action_plan 의 세 구간
    plan = result.get("action_plan")
    if not isinstance(plan, dict):
        problems.append("result.action_plan 이 객체가 아닙니다 — 후처리 미적용")
    else:
        need = set(interfaces.get("ActionPlanWindow", []))
        for window in ("단기", "중기", "장기"):
            w = plan.get(window)
            if not isinstance(w, dict):
                problems.append(f"action_plan.{window} 가 객체가 아닙니다 — 후처리 미적용")
            else:
                problems += _diff(f"action_plan.{window}", need, set(w.keys()))

    # 3) 런타임 검증기 상수 ↔ 인터페이스 (파일 내부 정합성)
    const_keys = set(parse_required_keys_const(ts_src))
    iface_keys = set(interfaces["AnalysisResult"])
    if const_keys != iface_keys:
        for k in sorted(iface_keys - const_keys):
            problems.append(f"REQUIRED_RESULT_KEYS 에 빠짐: {k} (런타임 검증이 이 필드를 놓친다)")
        for k in sorted(const_keys - iface_keys):
            problems.append(f"REQUIRED_RESULT_KEYS 에만 있음: {k}")

    # 4) 예시 응답 노후화
    parsed = parse_example(ts_src)
    if parsed is None:
        problems.append("EXAMPLE_SUCCESS 를 찾지 못했습니다")
    else:
        problems += _diff("EXAMPLE_SUCCESS.result",
                          set(result.keys()), set(parsed[0].get("result", {}).keys()))

    return problems


def write_example(ts_src: str, example: dict) -> str:
    """EXAMPLE_SUCCESS 리터럴을 실제 응답으로 교체한다."""
    parsed = parse_example(ts_src)
    if parsed is None:
        raise SystemExit("EXAMPLE_SUCCESS 를 찾지 못해 갱신할 수 없습니다")
    _, start, end = parsed
    return ts_src[:start] + json.dumps(example, ensure_ascii=False, indent=2) + ts_src[end:]


def main(argv: list[str]) -> int:
    with open(_TS_PATH, encoding="utf-8") as f:
        ts_src = f.read()

    example = build_example()
    problems = check(ts_src, example)

    if problems:
        print("스키마와 실제 응답이 어긋납니다:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    n = len(parse_interfaces(ts_src)["AnalysisResult"])
    print(f"일치 확인: result 최상위 {n}개 필드 · 중첩 8종 · "
          f"런타임 검증 상수 · EXAMPLE_SUCCESS")

    if "--write" in argv:
        with open(_TS_PATH, "w", encoding="utf-8") as f:
            f.write(write_example(ts_src, example))
        print("  갱신: schema/analysis_result.ts 의 EXAMPLE_SUCCESS")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
