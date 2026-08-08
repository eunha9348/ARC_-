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


# --------------------------------------------------------------------------
#  업계(산업)별 자소서 문체 프로필
# --------------------------------------------------------------------------
#  같은 '데이터 분석' 직무라도 증권사에 내는 자소서와 IT 플랫폼에 내는
#  자소서는 통하는 문체가 완전히 다르다. 직무(JOB_PROFILES)가 '무엇을 잘하는가'를
#  담당한다면, 업계(INDUSTRY_PROFILES)는 '어떤 결의 글이 먹히는가'를 담당한다.
#
#   voice        : 그 업계 자소서 특유의 문장 결/호흡
#   values       : 그 업계가 사람에게서 확인하려는 가치
#   evidence     : 어떤 종류의 근거가 설득력을 갖는가
#   taboo        : 그 업계에서 감점 요인이 되는 표현/태도
#   vocabulary   : 자연스럽게 배어 나오면 좋은 어휘 결
# --------------------------------------------------------------------------
INDUSTRY_PROFILES: dict[str, dict[str, Any]] = {
    "general": {
        "label": "일반",
        "voice": "담백하고 신뢰감 있는 문어체. 두괄식으로 핵심을 먼저 제시.",
        "values": ["직무 이해도", "성실성", "성장 가능성", "조직 적합성"],
        "evidence": "구체적 상황과 행동, 그리고 결과가 이어지는 서술",
        "taboo": "추상적 미사여구, 근거 없는 자기 확신",
        "vocabulary": "과장 없는 일상 업무 어휘",
    },
    "finance": {
        "label": "금융권(은행·증권·보험·자산운용·카드)",
        "voice": (
            "절제되고 정확한 문어체. 화려한 수사보다 '틀리지 않게 쓰는' 것이 신뢰를 준다. "
            "문장은 단정적이되 겸허하고, 호흡은 차분하게 유지한다."
        ),
        "values": ["신뢰성", "리스크 인식", "정합성·정확성", "윤리·규정 준수", "장기적 책임감"],
        "evidence": (
            "검증 가능한 수치와 그 수치를 얻은 방법론. 성과의 크기보다 "
            "'왜 그 수치를 믿을 수 있는지'를 함께 밝히는 서술이 더 강하다. "
            "실패·한계를 인지하고 통제한 경험은 감점이 아니라 가점이다."
        ),
        "taboo": (
            "튀는 개성 강조, 검증되지 않은 수치, 리스크를 가볍게 보는 뉘앙스, "
            "'혁신적으로 판을 뒤집겠다'류의 과격한 표현"
        ),
        "vocabulary": "고객 자산, 리스크 관리, 규제·컴플라이언스, 건전성, 신뢰, 정합성",
    },
    "it": {
        "label": "IT/플랫폼/테크",
        "voice": (
            "간결하고 직설적인 문어체. 격식보다 명료함이 우선이며, 겸양 표현을 "
            "남발하지 않는다. 기술 용어는 정확히 쓰되 과시하지 않는다."
        ),
        "values": ["오너십", "문제 정의 능력", "학습 속도", "자율성", "임팩트"],
        "evidence": (
            "문제 → 내가 내린 기술적 선택과 그 근거 → 지표 변화의 3단 구조. "
            "실패와 회고를 솔직하게 드러내는 서술이 오히려 신뢰를 준다."
        ),
        "taboo": (
            "'귀사의 무궁한 발전' 같은 형식적 관용구, 성과만 나열하고 판단 근거가 "
            "없는 서술, 회사를 일방적으로 찬양하는 문장"
        ),
        "vocabulary": "문제 정의, 가설 검증, 지표 개선, 트레이드오프, 회고, 사용자 임팩트",
    },
    "manufacturing": {
        "label": "제조/대기업(전자·중공업·화학·자동차)",
        "voice": (
            "정중하고 안정적인 문어체. 소제목을 활용한 정형화된 구성이 선호된다. "
            "조직 안에서 함께 일하는 사람으로 읽히도록 쓴다."
        ),
        "values": ["조직 융화", "성실성", "현장 이해", "안전 의식", "책임 완수"],
        "evidence": "현장의 문제를 직접 확인하고, 원인을 파고들어, 개선 수치로 증명한 경험",
        "taboo": "개인 성취만 부각하는 서술, 조직 절차를 가볍게 여기는 뉘앙스",
        "vocabulary": "공정, 품질, 개선, 표준화, 안전, 협업, 현장",
    },
    "public": {
        "label": "공공/공기업",
        "voice": (
            "격식 있고 명료한 문어체. 문항이 요구한 항목에 정확히 대응하는 것이 "
            "무엇보다 중요하다(NCS 기반 평가). 개인 성취보다 공적 기여로 프레이밍한다."
        ),
        "values": ["공익성", "청렴·윤리", "형평성", "규정 준수", "직무 적합성"],
        "evidence": "직무기술서의 능력단위에 대응하는 구체적 경험과 절차 준수 사례",
        "taboo": "사익 중심 동기, 규정을 우회한 성과, 특정 집단에 치우친 관점",
        "vocabulary": "공공성, 형평성, 절차 준수, 이해관계자, 국민 편익",
    },
    "consulting": {
        "label": "컨설팅/전문서비스",
        "voice": (
            "구조화된 문어체. 글의 전개 방식 자체가 사고력의 증거로 평가되므로, "
            "결론 먼저 제시하고 근거를 층위별로 정리한다."
        ),
        "values": ["구조적 사고", "가설 기반 문제해결", "커뮤니케이션", "임팩트"],
        "evidence": "문제를 분해한 기준과 그 기준을 선택한 이유, 그리고 도출한 결론",
        "taboo": "논리 비약, 근거 없이 결론만 제시, 장황한 배경 설명",
        "vocabulary": "가설, 구조화, 우선순위, 임팩트, 이해관계자, 의사결정",
    },
    "commerce": {
        "label": "커머스/유통/이커머스",
        "voice": "생동감 있되 성과는 숫자로 말하는 문어체. 고객 관점을 앞세운다.",
        "values": ["고객 관점", "실행 속도", "숫자 감각", "협업"],
        "evidence": "고객 문제 발견 → 빠른 실행 → 매출·전환 등 지표 변화",
        "taboo": "고객이 빠진 자기중심 서술, 실행 없이 아이디어만 나열",
        "vocabulary": "고객 경험, 전환율, 객단가, 리텐션, 실행",
    },
    "bio": {
        "label": "바이오/제약/헬스케어",
        "voice": "정밀하고 신중한 문어체. 근거와 절차를 빠짐없이 밝힌다.",
        "values": ["전문성", "정확성", "규제 이해", "윤리성", "재현성"],
        "evidence": "실험 설계와 재현 가능한 결과, 규정(GMP/임상 등) 준수 경험",
        "taboo": "데이터 과장, 절차 생략, 안전·윤리를 가볍게 다루는 태도",
        "vocabulary": "실험 설계, 재현성, 규제 준수, 데이터 무결성, 검증",
    },
}


#  회사명/직무명 문자열에서 업계를 추정하기 위한 키워드 사전.
#  ※ LLM 추측이 아니라 '문자열 포함 여부'로만 판단하는 결정적 매핑이다.
INDUSTRY_ALIASES = {
    # 금융권
    "증권": "finance", "은행": "finance", "카드": "finance", "보험": "finance",
    "자산운용": "finance", "캐피탈": "finance", "금융": "finance", "저축": "finance",
    "핀테크": "finance", "투자": "finance", "뱅크": "finance", "페이": "finance",
    "파이낸셜": "finance", "신탁": "finance", "손해보험": "finance",
    "securities": "finance", "bank": "finance", "asset": "finance",
    "capital": "finance", "insurance": "finance", "financial": "finance",
    # IT/플랫폼
    #  ※ 짧은 약어("it")는 digital 같은 단어에 부분 일치해 오탐을 내므로 쓰지 않는다.
    "소프트웨어": "it", "플랫폼": "it", "테크": "it", "개발": "it",
    "스타트업": "it", "아이티": "it", "정보기술": "it",
    "software": "it", "platform": "it", "labs": "it",
    # 제조/대기업
    "전자": "manufacturing", "중공업": "manufacturing", "화학": "manufacturing",
    "자동차": "manufacturing", "제조": "manufacturing", "반도체": "manufacturing",
    "디스플레이": "manufacturing", "물산": "manufacturing", "重": "manufacturing",
    # 공공
    #  ※ "청" 한 글자는 신청·청년 등에 부분 일치하므로 쓰지 않고, 기관명 단위로 매칭한다.
    "공사": "public", "공단": "public", "진흥원": "public", "재단": "public",
    "공공": "public", "정부": "public", "공기업": "public", "지자체": "public",
    "시청": "public", "구청": "public", "교육청": "public",
    # 컨설팅
    "컨설팅": "consulting", "consulting": "consulting", "회계법인": "consulting",
    # 커머스
    "커머스": "commerce", "유통": "commerce", "쇼핑": "commerce", "리테일": "commerce",
    "commerce": "commerce", "retail": "commerce",
    # 바이오
    "제약": "bio", "바이오": "bio", "헬스케어": "bio", "병원": "bio",
    "pharm": "bio", "bio": "bio",
}


def normalize_industry_key(industry: str) -> str:
    """업계 문자열을 표준 key 로 변환한다(모르면 general)."""
    if not industry:
        return "general"
    k = industry.strip().lower()
    if k in INDUSTRY_PROFILES:
        return k
    if k in INDUSTRY_ALIASES:
        return INDUSTRY_ALIASES[k]
    for alias, target in INDUSTRY_ALIASES.items():
        if alias in k:
            return target
    return "general"


def infer_industry(company: str = "", job: str = "") -> str:
    """회사명/직무명에서 업계를 추정한다.

    문자열 포함 여부만으로 판단하는 결정적 로직이며, 근거가 없으면
    'general' 을 돌려준다(추측해서 지어내지 않는다).
    """
    for source in (company or "", job or ""):
        key = normalize_industry_key(source)
        if key != "general":
            return key
    return "general"


def get_industry_profile(industry: str) -> dict[str, Any]:
    """표준화 후 업계 프로필 반환(없으면 general)."""
    key = normalize_industry_key(industry)
    profile = dict(INDUSTRY_PROFILES.get(key, INDUSTRY_PROFILES["general"]))
    profile["key"] = key
    return profile


def list_industry_keys() -> list[str]:
    return list(INDUSTRY_PROFILES.keys())


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
