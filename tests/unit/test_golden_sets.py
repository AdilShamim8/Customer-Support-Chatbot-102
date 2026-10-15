"""
Golden-set integrity tests - the eval gate is only as strong as its data.

If the JSONL files rot (malformed lines, duplicate IDs, missing flags),
ADR-0007's gate silently tests nothing. These tests fail loudly instead.
"""

import json
import pathlib

import pytest

EVAL_DIR = pathlib.Path("data/eval")
GOLDEN_FILES = [
    "golden_faq.jsonl",
    "golden_multihop.jsonl",
    "golden_adversarial.jsonl",
]

REQUIRED_FIELDS = {"question_id", "category", "question", "expected_answer", "answerable"}
VALID_CATEGORIES = {"faq", "multi_hop", "adversarial", "unanswerable", "ambiguous"}


def load_golden(path: pathlib.Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


@pytest.mark.parametrize("filename", GOLDEN_FILES)
class TestGoldenSetIntegrity:
    def test_file_exists_and_nonempty(self, filename):
        path = EVAL_DIR / filename
        assert path.exists(), f"{filename} missing - the eval gate has no data"
        assert load_golden(path), f"{filename} is empty"

    def test_every_record_has_required_fields(self, filename):
        for record in load_golden(EVAL_DIR / filename):
            missing = REQUIRED_FIELDS - set(record)
            assert not missing, f"{filename}: {record.get('question_id')} missing {missing}"

    def test_categories_are_valid(self, filename):
        for record in load_golden(EVAL_DIR / filename):
            assert (
                record["category"] in VALID_CATEGORIES
            ), f"{filename}: unknown category {record['category']!r}"

    def test_questions_are_substantive(self, filename):
        # One-word questions test nothing; adversarial cases still need
        # enough context to be adversarial ABOUT something
        for record in load_golden(EVAL_DIR / filename):
            assert len(record["question"]) >= 3

    def test_expected_answers_present_when_answerable(self, filename):
        for record in load_golden(EVAL_DIR / filename):
            if record["answerable"]:
                assert record[
                    "expected_answer"
                ].strip(), (
                    f"{filename}: answerable case {record['question_id']} has empty expected answer"
                )


class TestGoldenSetComposition:
    def test_ids_unique_across_all_sets(self):
        all_ids: list[str] = []
        for filename in GOLDEN_FILES:
            all_ids += [r["question_id"] for r in load_golden(EVAL_DIR / filename)]
        duplicates = {qid for qid in all_ids if all_ids.count(qid) > 1}
        assert not duplicates, f"Duplicate question IDs: {duplicates}"

    def test_unanswerable_cases_exist(self):
        """The refusal contract needs cases that MUST be declined."""
        all_records = [r for f in GOLDEN_FILES for r in load_golden(EVAL_DIR / f)]
        unanswerable = [r for r in all_records if not r["answerable"]]
        assert len(unanswerable) >= 5, "Safety floor too thin - add unanswerable cases"

    def test_adversarial_prompt_injection_exists(self):
        all_records = [r for f in GOLDEN_FILES for r in load_golden(EVAL_DIR / f)]
        injection_like = [
            r
            for r in all_records
            if "ignore" in r["question"].lower() or "system prompt" in r["question"].lower()
        ]
        assert injection_like, "No prompt-injection cases in the golden sets"
