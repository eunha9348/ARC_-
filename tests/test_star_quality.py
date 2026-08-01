"""
STAR 품질 채점 회귀 테스트 — 네트워크·API 키 불필요.

`python3 tests/test_star_quality.py` 로 단독 실행 가능.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hallucination_guard import (  # noqa: E402
    VerificationAudit,
    evaluate_star_entries,
    score_star_entry,
    validate_derived_fields,
)

_SOURCE = """\
2024.03~2024.08 데이터분석 동아리 DA 활동
회원 이탈 원인 분석 프로젝트에서 데이터 파트를 담당했습니다.
Python 으로 크롤러를 개발해 리뷰 8000건을 수집했습니다.
SQL 로 3년치 로그를 집계해 이탈 원인 3가지를 도출했습니다.
그 결과 재등록률이 18% 개선되었고 이 분석 방식이 이후 정기 운영에 채택되었습니다.
이 과정에서 가설을 먼저 세우고 데이터로 검증하는 순서가 중요하다는 것을 배웠습니다.
"""

# 연구에서 확인된 실패 패턴을 모두 담은 항목:
# 배경 과다, 공동 주어, 약한 동사, 방법 부재, 수치 없는 모호한 결과
_WEAK_ENTRY = {
    "title": "동아리 활동",
    "S": "제가 속한 동아리는 오랜 기간 운영되어 온 조직으로 매 학기 다양한 프로젝트를 "
         "진행해 왔으며 회원 규모도 상당했고 여러 파트가 협업하는 구조였습니다. "
         "그중 데이터 파트는 분석을 담당하는 조직이었습니다.",
    "T": "제가 속한 동아리는 오랜 기간 운영되어 온 조직으로 분석을 담당해야 했습니다.",
    "A": "우리는 프로젝트에 참여했고 함께 활동했습니다.",
    "R": "프로젝트가 성공적으로 마무리되어 큰 도움이 되었습니다.",
}

# 연구 기준을 모두 충족하는 항목
_STRONG_ENTRY = {
    "title": "회원 이탈 원인 분석",
    "S": "2024년 상반기 동아리 회원 이탈이 누적되던 상황이었습니다.",
    "T": "저는 데이터 파트에서 이탈 원인을 규명하는 과제를 맡았습니다.",
    "A": "제가 Python 으로 크롤러를 설계해 리뷰 8000건을 수집했고, "
         "SQL 로 3년치 로그를 집계하는 방식으로 코호트를 나눠 분석했습니다. "
         "이탈 시점 직전 행동 패턴을 기준으로 세 가지 가설을 세워 순차 검증했습니다.",
    "R": "이탈 원인 3가지를 도출해 재등록률을 18% 개선했고, "
         "이 분석 방식이 이후 정기 운영에 채택되었습니다.",
}


class TestScoring(unittest.TestCase):

    def test_weak_entry_gets_low_grade(self):
        q = score_star_entry(_WEAK_ENTRY)
        self.assertIn(q.grade, ("C", "D"), f"약한 항목이 {q.grade} 를 받음")
        failed = {c.key for c in q.failed}
        for expected in ("first_person", "strong_verb", "result_quantified",
                         "action_dominant", "no_vague"):
            self.assertIn(expected, failed, f"{expected} 미달을 잡지 못함")

    def test_strong_entry_gets_high_grade(self):
        q = score_star_entry(_STRONG_ENTRY)
        self.assertIn(q.grade, ("A", "B"),
                      f"강한 항목이 {q.grade} — 미달: {[c.key for c in q.failed]}")

    def test_action_dominance_measured(self):
        q = score_star_entry(_WEAK_ENTRY)
        crit = next(c for c in q.criteria if c.key == "action_dominant")
        self.assertFalse(crit.passed)
        self.assertTrue(crit.coaching)

    def test_communal_subject_flagged(self):
        entry = dict(_STRONG_ENTRY, A="우리는 크롤러를 개발했고 우리가 분석했습니다.")
        crit = next(c for c in score_star_entry(entry).criteria
                    if c.key == "first_person")
        self.assertFalse(crit.passed)

    def test_role_split_rescues_communal_subject(self):
        """공동 주어라도 역할 분담을 명시하면 감점하지 않는다."""
        entry = dict(_STRONG_ENTRY,
                     A="우리 팀은 3개 축으로 나누어 진행했고, 이 중 저는 "
                       "Python 으로 크롤러를 설계하는 부분을 담당했습니다.")
        crit = next(c for c in score_star_entry(entry).criteria
                    if c.key == "first_person")
        self.assertTrue(crit.passed)

    def test_vague_result_without_metric_fails(self):
        entry = dict(_STRONG_ENTRY, R="프로젝트가 성공적으로 마무리되었습니다.")
        keys = {c.key for c in score_star_entry(entry).failed}
        self.assertIn("no_vague", keys)
        self.assertIn("result_quantified", keys)

    def test_metric_rescues_vague_wording(self):
        """모호 표현이 있어도 수치로 뒷받침되면 통과."""
        entry = dict(_STRONG_ENTRY, R="재등록률이 18% 크게 개선되었고 이후 채택되었습니다.")
        crit = next(c for c in score_star_entry(entry).criteria if c.key == "no_vague")
        self.assertTrue(crit.passed)

    def test_method_detection(self):
        no_method = dict(_STRONG_ENTRY, A="제가 데이터를 살펴보고 원인을 찾았습니다.")
        self.assertFalse(next(c for c in score_star_entry(no_method).criteria
                              if c.key == "action_method").passed)
        self.assertTrue(next(c for c in score_star_entry(_STRONG_ENTRY).criteria
                             if c.key == "action_method").passed)

    def test_situation_task_overlap_flagged(self):
        crit = next(c for c in score_star_entry(_WEAK_ENTRY).criteria
                    if c.key == "slots_distinct")
        self.assertFalse(crit.passed)

    def test_every_failure_carries_coaching(self):
        for entry in (_WEAK_ENTRY, _STRONG_ENTRY):
            for c in score_star_entry(entry).failed:
                self.assertTrue(c.coaching, f"{c.key} 에 개선 지시가 없음")


class TestDerivedFields(unittest.TestCase):

    def test_headline_number_hallucination_removed(self):
        entry = dict(_STRONG_ENTRY,
                     headline="크롤러를 설계해 매출을 235% 끌어올림")
        notes = validate_derived_fields(entry, _SOURCE, VerificationAudit())
        self.assertIsNone(entry["headline"])
        self.assertTrue(any("235" in n for n in notes))

    def test_grounded_headline_survives(self):
        entry = dict(_STRONG_ENTRY,
                     headline="Python 크롤러로 리뷰 8000건을 분석해 재등록률 18% 개선")
        validate_derived_fields(entry, _SOURCE, VerificationAudit())
        self.assertIsNotNone(entry["headline"])

    def test_unsupported_lesson_removed(self):
        """원문에 없는 '배움'은 추측이므로 삭제된다."""
        entry = dict(_STRONG_ENTRY,
                     L="리더십의 중요성을 깨달았습니다",
                     L_source_quote="리더십의 중요성을 깨달았습니다")
        validate_derived_fields(entry, _SOURCE, VerificationAudit())
        self.assertIsNone(entry["L"])
        self.assertIsNone(entry["L_source_quote"])

    def test_supported_lesson_survives(self):
        entry = dict(
            _STRONG_ENTRY,
            L="가설을 먼저 세우고 데이터로 검증하는 순서의 중요성",
            L_source_quote="가설을 먼저 세우고 데이터로 검증하는 순서가 중요하다는 것을 배웠습니다",
        )
        validate_derived_fields(entry, _SOURCE, VerificationAudit())
        self.assertIsNotNone(entry["L"])


class TestPortfolioEvaluation(unittest.TestCase):

    def test_empty_input(self):
        r = evaluate_star_entries([], _SOURCE)
        self.assertEqual(r["evaluated"], 0)
        self.assertIn("없습니다", r["portfolio_verdict"])

    def test_distribution_and_top_fixes(self):
        audit = VerificationAudit()
        entries = [dict(_WEAK_ENTRY), dict(_STRONG_ENTRY)]
        r = evaluate_star_entries(entries, _SOURCE, audit)
        self.assertEqual(r["evaluated"], 2)
        self.assertEqual(sum(r["grade_distribution"].values()), 2)
        self.assertTrue(r["top_fixes"])
        # 채점 결과가 각 항목에 부착되어야 한다
        for e in entries:
            self.assertIn("grade", e["quality"])
            self.assertIn("verdict", e["quality"])

    def test_all_weak_verdict(self):
        r = evaluate_star_entries([dict(_WEAK_ENTRY)], _SOURCE)
        self.assertIn("보완", r["portfolio_verdict"])

    def test_quality_never_drops_entries(self):
        """품질 미달이라고 항목을 버리지 않는다 — 버리면 고칠 방법을 알 수 없다."""
        entries = [dict(_WEAK_ENTRY)]
        evaluate_star_entries(entries, _SOURCE)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["quality"]["grade"], "D")


if __name__ == "__main__":
    unittest.main(verbosity=2)
