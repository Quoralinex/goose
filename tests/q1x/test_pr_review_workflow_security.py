from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
REVIEW = (ROOT / ".github/workflows/q1x-pr-review.yml").read_text()


def extract_embedded_python(target):
    match = re.search(
        rf"cat > {re.escape(target)} <<'PY'\n(?P<body>.*?)\n          PY",
        REVIEW,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"embedded workflow script not found: {target}")
    return match.group("body")


class Q1XAssuranceClassifierTests(unittest.TestCase):
    def test_workflow_owns_single_classifier_and_runs_deterministic_self_tests(self):
        source = extract_embedded_python("/tmp/q1x-review/classify_assurance.py")
        self.assertIn("def classify(check_payload, status_payload, regex, require=True):", source)
        self.assertIn("def self_test():", source)
        for state in (
            "no-configured-independent-assurance",
            "pending",
            "completed-clean",
            "no-successful-independent-assurance",
            "adverse",
        ):
            self.assertIn(state, source)
        for conclusion in ("success", "skipped", "neutral", "failure"):
            self.assertIn(f'"{conclusion}"', source)
        self.assertIn("mixed-clean", source)
        self.assertIn("mixed-adverse", source)
        self.assertIn("python3 /tmp/q1x-review/classify_assurance.py --self-test", REVIEW)


class Q1XCheckRunCollectionTests(unittest.TestCase):
    def test_semantic_and_assurance_collection_paginate_all_check_runs(self):
        self.assertGreaterEqual(REVIEW.count("gh api --paginate --slurp"), 2)
        self.assertGreaterEqual(REVIEW.count("jq '{check_runs: [.[].check_runs[]]}'"), 2)

    def test_goose_must_complete_strictly_after_primary(self):
        semantic_source = extract_embedded_python("/tmp/q1x-review/verify_semantic_attestations.py")
        self.assertIn("if not primary_completed or not goose_completed:", semantic_source)
        self.assertIn("if goose_completed <= primary_completed:", semantic_source)
        self.assertIn("completed_at must be strictly later than", semantic_source)


class Q1XMergeAuthorityTests(unittest.TestCase):
    def _read_pinned_workflow(self, sha):
        target = f"{sha}:.github/workflows/q1x-pr-review.yml"
        shown = subprocess.run(
            ["git", "show", target],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if shown.returncode == 0:
            return shown.stdout

        fetched = subprocess.run(
            ["git", "fetch", "--no-tags", "--depth=1", "origin", sha],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            0,
            fetched.returncode,
            "immutable workflow commit is absent from the checkout and deterministic fetch failed: "
            + fetched.stderr,
        )

        shown = subprocess.run(
            ["git", "show", target],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            0,
            shown.returncode,
            "immutable workflow commit was fetched but workflow content is unavailable: " + shown.stderr,
        )
        return shown.stdout

    def test_merge_authority_is_base_controlled_and_sha_pinned(self):
        caller = (ROOT / ".github/workflows/q1x-goose-review.yml").read_text()
        self.assertIn("\n  pull_request_target:\n", caller)
        self.assertNotIn("\n  pull_request:\n", caller)
        match = re.search(
            r"uses:\s+Quoralinex/goose/\.github/workflows/q1x-pr-review\.yml@([0-9a-f]{40})",
            caller,
        )
        self.assertIsNotNone(match, "merge-authoritative reusable workflow must use an immutable SHA")
        pinned = self._read_pinned_workflow(match.group(1))
        self.assertEqual(REVIEW, pinned)
        self.assertNotIn("uses: ./.github/workflows/q1x-pr-review.yml", caller)


class Q1XLiveProviderScopeTests(unittest.TestCase):
    def test_q1x_security_tests_do_not_trigger_live_provider_credentials(self):
        smoke = (ROOT / ".github/workflows/pr-smoke-test.yml").read_text()
        self.assertIn("              - '!tests/q1x/**'", smoke)


if __name__ == "__main__":
    unittest.main()
