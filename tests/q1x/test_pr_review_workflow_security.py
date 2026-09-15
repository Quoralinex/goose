from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
REVIEW = (ROOT / ".github/workflows/q1x-pr-review.yml").read_text()

ADVERSE_CHECKS = {
    "failure",
    "cancelled",
    "timed_out",
    "action_required",
    "stale",
    "startup_failure",
}


def classify(checks=(), statuses=(), require=True):
    relevant = len(checks) + len(statuses)
    pending = sum(c[0] != "completed" for c in checks)
    pending += sum(s == "pending" for s in statuses)
    adverse = sum(c[0] == "completed" and c[1] in ADVERSE_CHECKS for c in checks)
    adverse += sum(s in {"failure", "error"} for s in statuses)
    successful = sum(c == ("completed", "success") for c in checks)
    successful += sum(s == "success" for s in statuses)
    if adverse:
        return "adverse"
    if relevant == 0:
        return "no-configured-independent-assurance" if require else "not-required"
    if pending:
        return "pending"
    if require and successful == 0:
        return "no-successful-independent-assurance"
    return "completed-clean"


class Q1XAssuranceClassifierTests(unittest.TestCase):
    def test_required_absent_fails(self):
        self.assertEqual("no-configured-independent-assurance", classify())

    def test_pending_is_not_clean(self):
        self.assertEqual("pending", classify(checks=[("in_progress", None)]))

    def test_success_is_clean(self):
        self.assertEqual("completed-clean", classify(checks=[("completed", "success")]))

    def test_skipped_is_not_success(self):
        self.assertEqual(
            "no-successful-independent-assurance",
            classify(checks=[("completed", "skipped")]),
        )
    def test_neutral_is_not_success(self):
        self.assertEqual(
            "no-successful-independent-assurance",
            classify(checks=[("completed", "neutral")]),
        )

    def test_adverse_fails(self):
        self.assertEqual("adverse", classify(checks=[("completed", "failure")]))

    def test_mixed_success_and_neutral_is_clean(self):
        self.assertEqual(
            "completed-clean",
            classify(checks=[("completed", "success"), ("completed", "neutral")]),
        )

    def test_mixed_success_and_adverse_fails(self):
        self.assertEqual(
            "adverse",
            classify(checks=[("completed", "success"), ("completed", "failure")]),
        )

    def test_workflow_tracks_explicit_success(self):
        for needle in (
            'successful_checks="$(jq',
            'select(.conclusion == "success")',
            'successful_statuses="$(jq',
            'select(.state == "success")',
            'successful=$((successful_checks + successful_statuses))',
            "state='no-successful-independent-assurance'",
            'successfulControls:$successful',
        ):
            self.assertIn(needle, REVIEW)


class Q1XMergeAuthorityTests(unittest.TestCase):
    def test_merge_authority_is_base_controlled_and_sha_pinned(self):
        caller = (ROOT / ".github/workflows/q1x-goose-review.yml").read_text()
        self.assertIn("\n  pull_request_target:\n", caller)
        self.assertNotIn("\n  pull_request:\n", caller)
        match = re.search(
            r"uses:\s+Quoralinex/goose/\.github/workflows/q1x-pr-review\.yml@([0-9a-f]{40})",
            caller,
        )
        self.assertIsNotNone(match, "merge-authoritative reusable workflow must use an immutable SHA")
        pinned = subprocess.run(
            ["git", "show", f"{match.group(1)}:.github/workflows/q1x-pr-review.yml"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertEqual(REVIEW, pinned)
        self.assertNotIn("uses: ./.github/workflows/q1x-pr-review.yml", caller)


class Q1XLiveProviderScopeTests(unittest.TestCase):
    def test_q1x_security_tests_do_not_trigger_live_provider_credentials(self):
        smoke = (ROOT / ".github/workflows/pr-smoke-test.yml").read_text()
        self.assertIn("              - '!tests/q1x/**'", smoke)


if __name__ == "__main__":
    unittest.main()
