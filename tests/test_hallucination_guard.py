"""
환각 가드 회귀 테스트 — 네트워크·API 키 불필요.

v2.0 에서 실제로 새어 나갔던 환각 유형을 재현 케이스로 고정한다.
`python3 tests/test_hallucination_guard.py` 로 단독 실행 가능.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hallucination_guard import (  # noqa: E402
    GroundingEvidence,
    VerificationAudit,
    assess_star_readiness,
    check_certification_name,
    extract_numbers,
    grounding_mentions,
    is_plausible_url,
    norm_name,
    numbers_grounded,
    quote_supported,
    scrub_model_urls,
    split_cert_grade,
    split_experience_blocks,
    validate_star_entries,
)


# ══════════════════════════════════════════════
#  H-3  없는 자격증 / 등급 환각
# ══════════════════════════════════════════════

class TestCertificationGuard(unittest.TestCase):

    def test_grade_split(self):
        self.assertEqual(split_cert_grade("컴퓨터활용능력 1급"), ("컴퓨터활용능력", "1급"))
        self.assertEqual(split_cert_grade("빅데이터분석기사"), ("빅데이터분석기사", None))
        self.assertEqual(split_cert_grade("한국사능력검정시험 심화"),
                         ("한국사능력검정시험", "심화"))

    def test_grade_hallucination_rejected(self):
        """등급 체계가 없는 자격증에 급수를 붙인 경우 — v2.0 이 놓치던 유형."""
        for bogus in ("빅데이터분석기사 2급", "정보처리기사 1급", "SQLD 2급",
                      "ADsP 1급", "정보보안기사 3급"):
            with self.subTest(bogus=bogus):
                check = check_certification_name(bogus)
                self.assertTrue(check.rejected,
                                f"{bogus} 가 통과되었습니다: {check.reason}")

    def test_invalid_grade_for_graded_cert(self):
        """실재 등급 체계가 있어도 없는 등급이면 제외."""
        check = check_certification_name("컴퓨터활용능력 3급")
        self.assertTrue(check.rejected)
        self.assertIn("유효 등급", check.reason)

    def test_valid_certifications_pass(self):
        for good in ("정보처리기사", "컴퓨터활용능력 1급", "SQLD", "ADsP",
                     "빅데이터분석기사", "사회조사분석사 2급", "한국사능력검정시험 심화",
                     "유통관리사 2급", "PMP", "TOEIC"):
            with self.subTest(good=good):
                check = check_certification_name(good)
                self.assertFalse(check.rejected, f"{good}: {check.reason}")
                self.assertEqual(check.verdict, "known")

    def test_alias_resolution(self):
        self.assertEqual(check_certification_name("SQL개발자").verdict, "known")
        self.assertEqual(check_certification_name("컴활 1급").verdict, "known")

    def test_unknown_cert_requires_search(self):
        """레지스트리 미등재 → 자동 통과가 아니라 검색 검증 대상."""
        check = check_certification_name("데이터마케팅전문가")
        self.assertTrue(check.needs_search)
        self.assertFalse(check.rejected)


# ══════════════════════════════════════════════
#  H-1  없는 링크 / URL 환각
# ══════════════════════════════════════════════

class TestUrlGuard(unittest.TestCase):

    def test_implausible_urls_rejected(self):
        for bad in (None, "", "null", "none", "미정", "javascript:alert(1)",
                    "data:text/html,x", "ftp://a.com/x", "notaurl",
                    "https://www.google.com/search?q=동아리",
                    "https://search.naver.com/search.naver?query=x"):
            with self.subTest(bad=bad):
                self.assertFalse(is_plausible_url(bad))

    def test_plausible_urls_accepted(self):
        for good in ("https://www.q-net.or.kr/man001.do",
                     "http://club.example.ac.kr/notice"):
            with self.subTest(good=good):
                self.assertTrue(is_plausible_url(good))

    def test_scrub_removes_unverified_urls(self):
        """모델이 규칙을 어기고 URL 을 출력해도 최종 산출물에는 남지 않는다."""
        payload = {
            "additional_recommendations": {
                "clubs_and_societies": [
                    {"name": "A동아리", "url": "https://fake-club.example.com"},
                    {"name": "B동아리", "official_url": "https://also-fake.example.com"},
                ],
                "certifications": [{"name": "X", "url": None}],
            },
            "verified_jobs": [{"company": "C", "url": "https://real.example.com/jobs/1"}],
        }
        removed = scrub_model_urls(payload, allowlist={"https://real.example.com/jobs/1"})
        self.assertEqual(removed, 2)
        clubs = payload["additional_recommendations"]["clubs_and_societies"]
        self.assertIsNone(clubs[0]["url"])
        self.assertIsNone(clubs[1]["official_url"])
        self.assertEqual(payload["verified_jobs"][0]["url"],
                         "https://real.example.com/jobs/1")


# ══════════════════════════════════════════════
#  그라운딩 강제
# ══════════════════════════════════════════════

class TestGroundingGate(unittest.TestCase):

    def test_no_grounding_means_unverified(self):
        """검색이 실제로 일어나지 않았으면 어떤 항목도 통과 못 한다."""
        empty = GroundingEvidence()
        self.assertFalse(empty.grounded)
        self.assertFalse(grounding_mentions("서울대학교 투자연구회", empty))

    def test_name_must_appear_in_evidence(self):
        ev = GroundingEvidence(
            uris=["https://example.ac.kr/club/quant"],
            titles=["서울대학교 퀀트투자학회 QSA 소개"],
            snippets=["QSA 는 서울대학교 퀀트투자학회입니다."],
        )
        self.assertTrue(grounding_mentions("서울대학교 퀀트투자학회", ev))
        # 검색 근거에 전혀 없는 이름은 모델이 뭐라 하든 통과 불가
        self.assertFalse(grounding_mentions("연세대학교 블록체인학회 YBC", ev))


# ══════════════════════════════════════════════
#  H-2  STAR 재구조화 / 창작
# ══════════════════════════════════════════════

_RICH_INPUT = """\
2024.03~2024.08 데이터분석 동아리 DA 활동
회원 이탈 원인 분석 프로젝트에서 데이터 파트를 담당했습니다.
Python 으로 크롤러를 개발해 리뷰 8000건을 수집했습니다.
SQL 로 3년치 로그를 집계해 이탈 원인 3가지를 도출했습니다.
그 결과 재등록률이 18% 개선되었습니다.

2023.09~2023.12 교내 마케팅 공모전 참가
팀장 역할로 5명 팀을 리드하며 설문 200건을 수행했습니다.
최종 발표에서 2위를 수상했습니다.
"""

_THIN_INPUT = """\
동아리 활동을 했습니다.

봉사활동 경험이 있습니다.

컴퓨터를 잘 다룹니다.
"""


class TestStarReadiness(unittest.TestCase):

    def test_block_splitting(self):
        blocks = split_experience_blocks(_RICH_INPUT)
        self.assertGreaterEqual(len(blocks), 2)

    def test_thin_input_blocks_star(self):
        """데이터가 부족하면 LLM 에 STAR 생성을 요청조차 하지 않는다."""
        r = assess_star_readiness(_THIN_INPUT)
        self.assertFalse(r.ready)
        self.assertTrue(r.coaching)
        self.assertIn("STAR", r.reason)

    def test_empty_input_blocks_star(self):
        r = assess_star_readiness("")
        self.assertFalse(r.ready)
        self.assertTrue(r.coaching)

    def test_rich_input_allows_star(self):
        r = assess_star_readiness(_RICH_INPUT)
        self.assertTrue(r.ready)
        self.assertGreaterEqual(len(r.eligible_blocks), 1)


class TestStarEvidenceBinding(unittest.TestCase):

    def test_quote_supported(self):
        self.assertTrue(quote_supported("리뷰 8000건을 수집했습니다", _RICH_INPUT))
        self.assertTrue(quote_supported("리뷰  8,000 건을 수집했습니다.", _RICH_INPUT))
        self.assertFalse(quote_supported("AWS 인프라를 설계했습니다", _RICH_INPUT))

    def test_number_hallucination_detected(self):
        ok, invented = numbers_grounded("매출을 47% 늘렸습니다", _RICH_INPUT)
        self.assertFalse(ok)
        self.assertIn("47", invented)
        ok2, _ = numbers_grounded("재등록률이 18% 개선", _RICH_INPUT)
        self.assertTrue(ok2)

    def test_fabricated_star_is_dropped(self):
        """원문에 없는 이야기를 지어낸 STAR 항목은 전부 폐기된다."""
        audit = VerificationAudit()
        entries = [{
            "title": "AWS 인프라 구축",
            "S": "대규모 트래픽 장애가 발생했습니다",
            "S_source_quote": "대규모 트래픽 장애가 발생했습니다",
            "T": "무중단 배포 체계를 만들어야 했습니다",
            "T_source_quote": "무중단 배포 체계를 만들어야 했습니다",
            "A": "Kubernetes 클러스터를 구성했습니다",
            "A_source_quote": "Kubernetes 클러스터를 구성했습니다",
            "R": "가용성을 99.9% 로 높였습니다",
            "R_source_quote": "가용성을 99.9% 로 높였습니다",
        }]
        kept, rejected = validate_star_entries(entries, _RICH_INPUT, audit)
        self.assertEqual(kept, [])
        self.assertEqual(len(rejected), 1)
        self.assertIn("Action", str(rejected[0]["unsupported_slots"]))

    def test_grounded_star_survives(self):
        audit = VerificationAudit()
        entries = [{
            "title": "회원 이탈 분석",
            "S": "동아리 회원 이탈이 문제였습니다",
            "S_source_quote": "회원 이탈 원인 분석 프로젝트에서 데이터 파트를 담당했습니다",
            "T": "이탈 원인을 규명해야 했습니다",
            "T_source_quote": "SQL 로 3년치 로그를 집계해 이탈 원인 3가지를 도출했습니다",
            "A": "Python 크롤러로 리뷰를 수집했습니다",
            "A_source_quote": "Python 으로 크롤러를 개발해 리뷰 8000건을 수집했습니다",
            "R": "재등록률 18% 개선",
            "R_source_quote": "그 결과 재등록률이 18% 개선되었습니다",
        }]
        kept, rejected = validate_star_entries(entries, _RICH_INPUT, audit)
        self.assertEqual(len(kept), 1)
        self.assertEqual(rejected, [])
        self.assertIn("A", kept[0]["evidence_status"]["supported_slots"])
        self.assertIn("R", kept[0]["evidence_status"]["supported_slots"])

    def test_restructuring_only_is_flagged(self):
        """네 슬롯이 같은 원문 문장을 돌려쓴 경우 = '단순 재구조화' 경고."""
        audit = VerificationAudit()
        same = "Python 으로 크롤러를 개발해 리뷰 8000건을 수집했습니다"
        entries = [{
            "title": "크롤러 개발",
            "S": "크롤러가 필요했습니다",
            "S_source_quote": same,
            "T": "리뷰를 모아야 했습니다",
            "T_source_quote": same,
            "A": "Python 으로 크롤러를 개발했습니다",
            "A_source_quote": same,
            "R": "리뷰 8000건을 수집했습니다",
            "R_source_quote": same,
        }]
        kept, _ = validate_star_entries(entries, _RICH_INPUT, audit)
        self.assertEqual(len(kept), 1)
        self.assertTrue(kept[0]["evidence_status"]["restructuring_only"])
        self.assertIn("재배치", kept[0]["quality_warning"])

    def test_invented_number_slot_is_stripped(self):
        audit = VerificationAudit()
        entries = [{
            "title": "회원 이탈 분석",
            "S": "이탈이 문제였습니다",
            "S_source_quote": "회원 이탈 원인 분석 프로젝트에서 데이터 파트를 담당했습니다",
            "T": "원인 규명",
            "T_source_quote": "SQL 로 3년치 로그를 집계해 이탈 원인 3가지를 도출했습니다",
            "A": "크롤러 개발",
            "A_source_quote": "Python 으로 크롤러를 개발해 리뷰 8000건을 수집했습니다",
            "R": "매출을 235% 끌어올렸습니다",
            "R_source_quote": "그 결과 재등록률이 18% 개선되었습니다",
        }]
        kept, rejected = validate_star_entries(entries, _RICH_INPUT, audit)
        # R 이 수치 환각으로 삭제되면 A+R 조건 미달 → 항목 폐기
        self.assertEqual(kept, [])
        self.assertIn("235", str(rejected[0]["unsupported_slots"]))


# ══════════════════════════════════════════════
#  기타 유틸
# ══════════════════════════════════════════════

class TestUtils(unittest.TestCase):

    def test_norm_name_matching(self):
        self.assertEqual(norm_name("(사)한국 데이터 산업 진흥원"),
                         norm_name("사한국데이터산업진흥원"))
        self.assertEqual(norm_name("SQL-D"), norm_name("sqld"))

    def test_extract_numbers(self):
        self.assertEqual(extract_numbers("리뷰 8,000건 18% 개선"), {"8000", "18"})

    def test_audit_summary(self):
        a = VerificationAudit()
        a.kept("clubs", "A", "ok")
        a.dropped("clubs", "B", "no")
        a.degraded("star", "C", "meh")
        s = a.summary()
        self.assertEqual(s["total_kept"], 1)
        self.assertEqual(s["total_dropped"], 1)
        self.assertEqual(s["total_degraded"], 1)
        self.assertEqual(s["by_stage"]["clubs"]["dropped"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
