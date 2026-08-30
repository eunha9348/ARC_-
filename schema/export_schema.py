"""
schema/export_schema.py
============================================================================
응답 스키마 ↔ 실제 코드 출력의 일치 검사 + 예시 응답 생성

스키마 문서는 손으로 관리하면 반드시 코드와 어긋난다. 실제로 v1.1 → v1.2 에서
후처리가 필드 8개를 추가하고 action_plan 구조를 바꿨지만, 프롬프트 템플릿의
JSON 예시는 그대로여서 두 곳이 서로 다른 형태를 말하고 있었다.

이 스크립트는 career_individual 의 실제 후처리 파이프라인을 통과시킨 응답을
스키마의 required 목록과 대조해, 어긋나면 실패한다. CI 나 배포 전에 돌리면
"프론트에 준 스키마와 백엔드 실제 응답이 다른" 사고를 막을 수 있다.

사용법:
  python schema/export_schema.py            # 검사만
  python schema/export_schema.py --write    # 검사 + 예시 응답 파일 갱신
============================================================================
"""

from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
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


def build_example() -> dict:
    """실제 후처리 파이프라인을 통과시킨 예시 응답 envelope."""
    tc = ci.TimeContext()
    time_facts = ci.extract_time_facts(_SAMPLE_INPUT, tc)
    result = ci.postprocess_result(json.loads(json.dumps(_LLM_RESPONSE)), tc, time_facts)
    result["embedding_dim"] = 3072

    payload = {k: v for k, v in result.items() if k not in ("status", "vector")}
    return {"status": "success", "vector": [0.0123, -0.0456, 0.0789], "result": payload}


def _collect_required(schema: dict, ref: str) -> list[str]:
    node = schema["$defs"][ref]
    return node.get("required", [])


def check(schema: dict, example: dict) -> list[str]:
    """스키마 required 목록과 실제 출력 키를 양방향 대조."""
    problems: list[str] = []
    result = example["result"]

    required = set(_collect_required(schema, "result"))
    actual = set(result.keys())

    for missing in sorted(required - actual):
        problems.append(f"스키마에는 있으나 실제 응답에 없음: result.{missing}")
    for extra in sorted(actual - required):
        problems.append(f"실제 응답에 있으나 스키마에 없음: result.{extra}")

    # 중첩 객체도 같은 방식으로 대조
    nested = [
        ("action_plan", None), ("time_context", "timeContext"),
        ("input_time_resolution", "timeResolution"), ("validation", "validation"),
        ("deep_analysis", "deepAnalysis"), ("item_strengths", "itemStrengths"),
        ("item_diagnosis", "itemDiagnosis"), ("star_format", "starFormat"),
    ]
    for key, ref in nested:
        value = result.get(key)
        if not isinstance(value, dict):
            continue
        if key == "action_plan":
            for window in ("단기", "중기", "장기"):
                w = value.get(window)
                if not isinstance(w, dict):
                    problems.append(f"action_plan.{window} 가 객체가 아님 — 후처리 미적용")
                    continue
                need = set(_collect_required(schema, "actionPlanWindow"))
                if need - set(w.keys()):
                    problems.append(f"action_plan.{window} 필드 누락: {sorted(need - set(w.keys()))}")
            continue
        need = set(_collect_required(schema, ref))
        have = set(value.keys())
        for missing in sorted(need - have):
            problems.append(f"스키마에는 있으나 실제 응답에 없음: {key}.{missing}")
        for extra in sorted(have - need):
            problems.append(f"실제 응답에 있으나 스키마에 없음: {key}.{extra}")

    return problems


def main(argv: list[str]) -> int:
    with open(os.path.join(_HERE, "analysis_result.schema.json"), encoding="utf-8") as f:
        schema = json.load(f)

    example = build_example()
    problems = check(schema, example)

    if problems:
        print("스키마와 실제 응답이 어긋납니다:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    n = len(_collect_required(schema, "result"))
    print(f"일치 확인: result 최상위 {n}개 필드 + 중첩 객체 8종")

    if "--write" in argv:
        for name, data in [
            ("example_success.json", example),
            ("example_error.json",
             {"status": "error",
              "message": "입력 데이터가 너무 짧습니다. 분석할 경력/자격증/활동을 입력해주세요."}),
        ]:
            path = os.path.join(_HERE, name)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            print(f"  갱신: schema/{name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
