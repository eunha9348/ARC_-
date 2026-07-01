"""
core/job_profiles.py
============================================================================
직무별 자소서 "스타일 / 양식 / HR 평가 포인트" 정의.

- 이 사전(JOB_PROFILES)이 직무별 차별화의 핵심이다.
- 생성(generator), 교정 제안(reviewer), 액션플랜(action_plan) 모두
  여기 정의된 직무 특성을 참조한다.
- region("KR"/"US")에 따라 자소서/레주메 문화 차이를 덧입힌다.
"""

from __future__ import annotations

from typing import Any


# --------------------------------------------------------------------------
#  한국형 vs 미국형 문화 차이 (모든 직무에 공통 적용되는 레이어)
# --------------------------------------------------------------------------
REGION_STYLE = {
    "KR": {
        "label": "한국형 자기소개서",
        "guidance": (
            "- 문항별(지원동기/성장과정/성격의 장단점/입사 후 포부 등) 서술형 구성.\n"
            "- 존댓말/문어체, 겸손하되 근거 있는 자신감.\n"
            "- 두괄식(핵심 문장 먼저) + 구체적 경험 + 회사/직무 연결 마무리.\n"
            "- 정량적 성과(숫자)와 STAR(상황-과제-행동-결과) 구조 선호.\n"
            "- 과장/추상적 미사여구 지양, 사실 기반 스토리텔링."
        ),
    },
    "US": {
        "label": "US-style Cover Letter",
        "guidance": (
            "- One-page business letter format (greeting, 3~4 paragraphs, closing).\n"
            "- Confident, achievement-oriented, action-verb driven.\n"
            "- Quantified impact ('increased X by Y%'), tailored to the role.\n"
            "- Directly map your experience to the job description keywords.\n"
            "- Concise, no personal/family background, professional tone."
        ),
    },
}


# --------------------------------------------------------------------------
#  직무별 프로필
#   competencies : HR/현업이 중점적으로 보는 핵심 역량
#   hr_focus     : 인사팀이 자소서에서 '확인하려는' 것
#   tone         : 권장 문체/톤
#   structure    : 권장 자소서 구성(문항/문단 흐름)
#   keywords     : 자연스럽게 녹이면 좋은 키워드
#   good_signals : 강한 인상을 주는 활동/경험(액션플랜 기반)
# --------------------------------------------------------------------------
JOB_PROFILES: dict[str, dict[str, Any]] = {
    "general": {
        "label": "일반/공통",
        "competencies": ["문제해결", "성실성", "협업", "성장의지"],
        "hr_focus": ["직무 이해도", "조직 적합성", "성장 가능성", "진정성"],
        "tone": "신뢰감 있고 담백한 문어체, 두괄식",
        "structure": ["핵심 강점 요약", "구체적 경험(STAR)", "직무/회사 연결", "포부"],
        "keywords": ["직무 역량", "협업", "성과", "학습"],
        "good_signals": ["직무 연관 프로젝트", "정량 성과", "지속적 학습 이력"],
    },
    "backend": {
        "label": "백엔드 개발",
        "competencies": ["자료구조/알고리즘", "데이터베이스 설계", "API/서버 아키텍처",
                          "성능 최적화", "트러블슈팅"],
        "hr_focus": ["기술 깊이", "시스템적 사고", "협업(코드리뷰/Git)", "장애 대응 경험"],
        "tone": "논리적·정량적, 기술 용어를 정확히 사용하되 과시하지 않음",
        "structure": ["기술 문제 정의", "설계/구현 선택과 근거", "성능·장애 개선 수치",
                      "협업 방식", "성장 방향"],
        "keywords": ["트래픽", "레이턴시", "쿼리 최적화", "테스트 커버리지", "장애 복구"],
        "good_signals": ["대용량 트래픽 처리 경험", "오픈소스 기여", "부하테스트/모니터링 구축",
                         "코드리뷰 문화 경험"],
    },
    "frontend": {
        "label": "프론트엔드 개발",
        "competencies": ["UI/UX 구현", "상태관리", "성능(렌더링/번들)", "접근성/크로스브라우징"],
        "hr_focus": ["사용자 관점", "협업(디자이너/기획)", "코드 품질", "최신 생태계 이해"],
        "tone": "사용자 가치 중심 + 기술적 근거",
        "structure": ["사용자 문제", "구현/최적화 선택", "지표 개선(로딩/전환율)", "협업", "성장"],
        "keywords": ["렌더링 최적화", "웹 성능", "컴포넌트 설계", "접근성", "전환율"],
        "good_signals": ["Lighthouse 점수 개선", "디자인시스템 구축", "실사용자 A/B 테스트"],
    },
    "data": {
        "label": "데이터 분석/사이언스",
        "competencies": ["통계/분석", "SQL/데이터 파이프라인", "머신러닝", "인사이트 도출/시각화"],
        "hr_focus": ["가설-검증 사고", "비즈니스 임팩트로 연결", "커뮤니케이션", "재현성"],
        "tone": "가설→분석→결론의 논리 흐름, 수치로 말하기",
        "structure": ["문제/가설", "데이터·방법", "분석 결과(수치)", "의사결정 기여", "한계와 개선"],
        "keywords": ["가설검정", "지표(KPI)", "실험설계", "예측 정확도", "의사결정"],
        "good_signals": ["실제 지표를 움직인 분석", "Kaggle/공모전", "대시보드 운영", "A/B 테스트 설계"],
    },
    "pm": {
        "label": "기획/PM/PO",
        "competencies": ["문제 정의", "우선순위/로드맵", "이해관계자 조율", "데이터 기반 의사결정"],
        "hr_focus": ["오너십", "커뮤니케이션", "실행력", "성과 책임"],
        "tone": "명료하고 구조적, 결과와 학습 강조",
        "structure": ["해결한 문제", "가설과 우선순위", "실행/협업", "성과 지표", "배운 점"],
        "keywords": ["로드맵", "리텐션", "전환율", "우선순위", "이해관계자"],
        "good_signals": ["0→1 프로덕트 출시", "지표 개선 리드", "사이드 프로젝트 운영"],
    },
    "marketing": {
        "label": "마케팅",
        "competencies": ["시장/고객 이해", "캠페인 기획·실행", "퍼포먼스 분석", "브랜드 커뮤니케이션"],
        "hr_focus": ["창의성+데이터", "실행 성과(ROI)", "트렌드 감각", "협업"],
        "tone": "설득력 있고 생동감 있되 성과는 숫자로",
        "structure": ["타깃/문제", "캠페인 아이디어", "실행", "성과(전환/ROAS)", "인사이트"],
        "keywords": ["ROAS", "전환율", "타깃팅", "콘텐츠", "그로스"],
        "good_signals": ["실제 캠페인 성과 수치", "SNS 채널 운영 성장", "그로스 실험"],
    },
    "sales": {
        "label": "영업/세일즈",
        "competencies": ["고객 관계", "협상/설득", "목표 달성", "시장 이해"],
        "hr_focus": ["목표 지향성", "실적", "끈기/회복탄력성", "신뢰 형성"],
        "tone": "적극적·자신감, 실적 중심",
        "structure": ["목표/도전", "접근 전략", "실행", "실적(수치)", "관계·신뢰"],
        "keywords": ["목표 달성률", "신규 고객", "매출 성장", "협상"],
        "good_signals": ["매출/실적 달성 경험", "고객 확보 사례", "영업 인턴십"],
    },
    "hr": {
        "label": "인사/HR",
        "competencies": ["채용/평가", "조직문화", "노무/제도 이해", "데이터 기반 HR"],
        "hr_focus": ["사람에 대한 통찰", "공정성", "커뮤니케이션", "제도 실행력"],
        "tone": "균형감 있고 신뢰가는 문체",
        "structure": ["사람/조직 문제", "제도·프로그램 기획", "실행/조율", "성과", "가치관"],
        "keywords": ["채용", "온보딩", "조직문화", "리텐션", "제도 개선"],
        "good_signals": ["채용/교육 프로그램 운영", "설문·데이터로 문화 개선", "동아리 운영"],
    },
    "finance": {
        "label": "재무/회계",
        "competencies": ["재무제표 이해", "정확성", "분석/예측", "규정 준수"],
        "hr_focus": ["꼼꼼함/정확성", "윤리성", "분석력", "책임감"],
        "tone": "정확하고 신중, 근거 중심",
        "structure": ["과제", "분석/처리", "정확성 확보 방법", "성과", "직업윤리"],
        "keywords": ["재무분석", "예산", "결산", "리스크", "규정준수"],
        "good_signals": ["재무 관련 자격증", "회계 실무/인턴", "재무모델링 프로젝트"],
    },
    "design": {
        "label": "디자인(UX/UI/그래픽)",
        "competencies": ["문제 정의", "사용자 리서치", "비주얼/인터랙션", "협업"],
        "hr_focus": ["문제해결형 디자인", "포트폴리오 근거", "협업", "성과 연결"],
        "tone": "사용자·문제 중심, 담백하게",
        "structure": ["사용자 문제", "리서치/컨셉", "디자인 결정 근거", "결과(지표)", "회고"],
        "keywords": ["사용성", "프로토타입", "디자인시스템", "전환율", "리서치"],
        "good_signals": ["실사용성 개선 사례", "디자인시스템 구축", "사용자 인터뷰"],
    },
    "research": {
        "label": "연구개발(R&D)",
        "competencies": ["전공 전문성", "실험설계", "논리적 문제해결", "논문/특허"],
        "hr_focus": ["전문 깊이", "끈기", "재현성/정직성", "실용화 연결"],
        "tone": "정밀하고 논리적, 근거·데이터 중심",
        "structure": ["연구 문제", "가설/방법", "실험·결과", "의의/한계", "발전 방향"],
        "keywords": ["실험설계", "재현성", "논문", "특허", "성능 개선"],
        "good_signals": ["논문/학회 발표", "연구 인턴", "특허", "실험 자동화"],
    },
    "operations": {
        "label": "생산/품질/운영",
        "competencies": ["공정 이해", "품질관리(QC/QA)", "개선(Lean/6시그마)", "안전"],
        "hr_focus": ["현장 감각", "개선 마인드", "책임감", "협업"],
        "tone": "실무적·구체적, 개선 수치 강조",
        "structure": ["현장 문제", "원인 분석", "개선 실행", "성과(불량률/생산성)", "협업"],
        "keywords": ["불량률", "생산성", "공정개선", "표준화", "안전"],
        "good_signals": ["공정/품질 개선 성과", "현장 실습", "6시그마/QC 자격"],
    },
}


ALIASES = {
    "서버": "backend", "server": "backend", "be": "backend", "백엔드": "backend",
    "프론트": "frontend", "fe": "frontend", "web": "frontend", "프론트엔드": "frontend",
    "데이터분석": "data", "데이터사이언스": "data", "ds": "data", "ml": "data", "ai": "data",
    "프로덕트": "pm", "po": "pm", "product": "pm", "기획": "pm",
    "마케터": "marketing", "growth": "marketing", "그로스": "marketing",
    "세일즈": "sales", "영업": "sales",
    "인사": "hr", "피플": "hr", "people": "hr",
    "회계": "finance", "재무": "finance", "accounting": "finance",
    "ux": "design", "ui": "design", "디자이너": "design",
    "연구": "research", "rnd": "research", "r&d": "research",
    "생산": "operations", "품질": "operations", "qa": "operations", "qc": "operations",
}


def normalize_job_key(job_key: str) -> str:
    """사용자가 넣은 직무 문자열을 표준 key 로 변환한다."""
    if not job_key:
        return "general"
    k = job_key.strip().lower()
    if k in JOB_PROFILES:
        return k
    if k in ALIASES:
        return ALIASES[k]
    # 부분 일치 시도
    for alias, target in ALIASES.items():
        if alias in k:
            return target
    return "general"


def get_job_profile(job_key: str) -> dict[str, Any]:
    """표준화 후 직무 프로필 반환(없으면 general)."""
    key = normalize_job_key(job_key)
    profile = dict(JOB_PROFILES.get(key, JOB_PROFILES["general"]))
    profile["key"] = key
    return profile


def get_region_style(region: str) -> dict[str, str]:
    r = (region or "KR").upper()
    return REGION_STYLE.get(r, REGION_STYLE["KR"])


def list_job_keys() -> list[str]:
    return list(JOB_PROFILES.keys())
