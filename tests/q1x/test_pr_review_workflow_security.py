from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
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


class Q1XAssuranceResilienceTests(unittest.TestCase):
    def test_transient_collection_and_classifier_failures_are_retryable(self):
        self.assertIn("for attempt in $(seq 1 46); do", REVIEW)
        self.assertIn('if ! collect_check_runs > "$check_runs_tmp"; then', REVIEW)
        self.assertIn('retry_collection_failure "check-runs" "$attempt"', REVIEW)
        self.assertRegex(
            REVIEW,
            r'if ! gh api "repos/\$GITHUB_REPOSITORY/commits/\$EXPECTED_HEAD/status" \\\n\s+> "\$status_tmp"; then',
        )
        self.assertIn('retry_collection_failure "status" "$attempt"', REVIEW)
        self.assertIn('> "$result_tmp"; then', REVIEW)
        self.assertIn('retry_collection_failure "classifier" "$attempt"', REVIEW)
        self.assertIn('if [ "$attempt" -eq 46 ]; then', REVIEW)

        match = re.search(
            r"          retry_collection_failure\(\) \{\n(?P<body>.*?)\n          \}",
            REVIEW,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "retry helper function is missing")
        retry_source = "retry_collection_failure() {\n" + textwrap.dedent(match.group("body")) + "\n}"
        for stage in ("check-runs", "status", "classifier"):
            with self.subTest(stage=stage):
                script = "\n".join(
                    [
                        "set -euo pipefail",
                        "sleep() { :; }",
                        "write_collection_error_result() { :; }",
                        retry_source,
                        "attempts=0",
                        "success=0",
                        "source_cmd() { attempts=$((attempts + 1)); [ \"$attempts\" -gt 1 ]; }",
                        "for attempt in 1 2; do",
                        "  if ! source_cmd; then",
                        f'    if retry_collection_failure "{stage}" "$attempt"; then continue; else break; fi',
                        "  fi",
                        "  success=1",
                        "  break",
                        "done",
                        'test "$success" -eq 1',
                        'test "$attempts" -eq 2',
                    ]
                )
                completed = subprocess.run(
                    ["bash", "-c", script],
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(0, completed.returncode, completed.stderr)

    def test_summary_normalizes_missing_empty_and_malformed_json(self):
        match = re.search(
            r"          normalize_json_file\(\) \{\n(?P<body>.*?)\n          \}",
            REVIEW,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "summary JSON normalizer function is missing")
        function_source = "normalize_json_file() {\n" + textwrap.dedent(match.group("body")) + "\n}"
        fallback = '{"schema":"q1x.collection-error.v1","state":"collection-error"}'
        for initial in (None, "", "{not-json"):
            with self.subTest(initial=initial):
                with tempfile.TemporaryDirectory() as temp_dir:
                    target = Path(temp_dir) / "evidence.json"
                    if initial is not None:
                        target.write_text(initial)
                    script = "\n".join(
                        [
                            "set -euo pipefail",
                            function_source,
                            'normalize_json_file "$1" "$2"',
                            'jq -e \'.state == "collection-error"\' "$1" >/dev/null',
                        ]
                    )
                    completed = subprocess.run(
                        ["bash", "-c", script, "_", str(target), fallback],
                        cwd=ROOT,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(0, completed.returncode, completed.stderr)



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
        pinned_sha = match.group(1)
        pinned = self._read_pinned_workflow(pinned_sha)
        self.assertNotIn("uses: ./.github/workflows/q1x-pr-review.yml", caller)

        authority_markers = (
            "q1x/ordinary-chat-primary",
            "q1x/goose-independent-review",
            "primaryAttestationDigest",
            "TRUSTED_REVIEWER_APP_ID",
            "attestation digest mismatch",
            "completed_at must be strictly later than",
        )
        for source in (pinned, REVIEW):
            for marker in authority_markers:
                self.assertIn(marker, source)

        if REVIEW != pinned:
            allowed = {
                ".github/workflows/q1x-pr-review.yml",
                "tests/q1x/test_pr_review_workflow_security.py",
            }
            history = subprocess.run(
                ["git", "rev-list", "--all", "--", ".github/workflows/q1x-pr-review.yml"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
            staged = False
            for commit in history:
                parent = subprocess.run(
                    ["git", "rev-parse", f"{commit}^"],
                    cwd=ROOT, check=False, capture_output=True, text=True,
                )
                if parent.returncode != 0:
                    continue
                before = subprocess.run(
                    ["git", "show", f"{parent.stdout.strip()}:.github/workflows/q1x-pr-review.yml"],
                    cwd=ROOT, check=False, capture_output=True, text=True,
                )
                after = subprocess.run(
                    ["git", "show", f"{commit}:.github/workflows/q1x-pr-review.yml"],
                    cwd=ROOT, check=False, capture_output=True, text=True,
                )
                if before.returncode != 0 or after.returncode != 0:
                    continue
                if before.stdout != pinned or after.stdout != REVIEW:
                    continue
                changed = subprocess.run(
                    ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit],
                    cwd=ROOT, check=True, capture_output=True, text=True,
                ).stdout.splitlines()
                if set(changed).issubset(allowed):
                    staged = True
                    break
            self.assertTrue(
                staged,
                "an unpinned reusable-workflow update must be one bounded workflow/test commit from the currently pinned content",
            )


class Q1XLiveProviderScopeTests(unittest.TestCase):
    def test_q1x_security_tests_do_not_trigger_live_provider_credentials(self):
        smoke = (ROOT / ".github/workflows/pr-smoke-test.yml").read_text()
        self.assertIn("              - '!tests/q1x/**'", smoke)


if __name__ == "__main__":
    unittest.main()
