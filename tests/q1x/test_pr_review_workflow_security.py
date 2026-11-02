from pathlib import Path
import hashlib
import json
import os
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
    def test_real_codeql_job_names_count_only_from_github_actions(self):
        source = textwrap.dedent(extract_embedded_python("/tmp/q1x-review/classify_assurance.py"))
        namespace = {"__name__": "q1x_assurance_test"}
        exec(source, namespace)
        matcher = re.search(r"regex='([^']+)'", REVIEW)
        self.assertIsNotNone(matcher)
        regex = matcher.group(1)
        head = "0123456789abcdef0123456789abcdef01234567"
        run = {"id": 7, "path": "dynamic/github-code-scanning/codeql", "event": "dynamic",
               "head_sha": head, "repository": {"full_name": "Quoralinex/goose"}}
        neutral = {"name": "CodeQL", "status": "completed", "conclusion": "neutral"}
        analysis = {"name": "Analyze (python)", "status": "completed", "conclusion": "success",
                    "app": {"slug": "github-actions"}, "id": 42,
                    "details_url": "https://github.com/Quoralinex/goose/actions/runs/7/job/42"}
        classify = namespace["classify"]

        def state(*checks, observed_run=run, statuses=()):
            def lookup(run_id, repository):
                self.assertEqual(run_id, 7)
                self.assertEqual(repository, "Quoralinex/goose")
                return observed_run

            return classify({"check_runs": list(checks)}, {"statuses": list(statuses)}, regex,
                            repo="Quoralinex/goose", head=head,
                            run_lookup=lookup)["state"]

        self.assertEqual(state(neutral), "no-configured-independent-assurance")
        for publisher in ("github-actions", "untrusted-app"):
            plain_success = {**neutral, "conclusion": "success", "app": {"slug": publisher}}
            self.assertEqual(state(plain_success), "no-configured-independent-assurance")
        self.assertEqual(state(statuses=[{"context": "CodeQL", "state": "success"}]),
                         "no-configured-independent-assurance")
        self.assertEqual(state(neutral, analysis), "completed-clean")
        self.assertEqual(state(neutral, {**analysis, "app": {"slug": "untrusted-app"}}),
                         "no-configured-independent-assurance")
        self.assertEqual(state(neutral, analysis, observed_run={**run, "path": ".github/workflows/fake.yml"}),
                         "no-configured-independent-assurance")
        self.assertEqual(state(neutral, analysis, observed_run={**run, "head_sha": "f" * 40}),
                         "no-configured-independent-assurance")
        self.assertEqual(state(neutral, analysis, observed_run={**run, "id": 8}),
                         "no-configured-independent-assurance")
        self.assertEqual(state(neutral, analysis,
                               observed_run={**run, "repository": {"full_name": "Quoralinex/other"}}),
                         "no-configured-independent-assurance")
        self.assertEqual(state(neutral, analysis, observed_run={**run, "event": "pull_request"}),
                         "no-configured-independent-assurance")
        self.assertEqual(state(neutral, analysis, {"name": "Analyze (rust)", "status": "in_progress",
                                                   "app": {"slug": "github-actions"}, "id": 43,
                                                   "details_url": "https://github.com/Quoralinex/goose/actions/runs/7/job/43"}),
                         "pending")
        self.assertEqual(state(neutral, analysis, {"name": "Analyze (rust)", "status": "completed",
                                                   "conclusion": "failure", "app": {"slug": "github-actions"},
                                                   "id": 43, "details_url": "https://github.com/Quoralinex/goose/actions/runs/7/job/43"}),
                         "adverse")

    def test_workflow_owns_single_classifier_and_runs_deterministic_self_tests(self):
        source = extract_embedded_python("/tmp/q1x-review/classify_assurance.py")
        self.assertIn("def classify(check_payload, status_payload, regex, require=True,", source)
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


def run_semantic_verifier(check_payload, existing_result=None):
    source = textwrap.dedent(extract_embedded_python("/tmp/q1x-review/verify_semantic_attestations.py"))
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "semantic-check-runs.json").write_text(json.dumps(check_payload))
        if existing_result is not None:
            (root / "semantic-review-result.json").write_text(json.dumps(existing_result))
        completed = subprocess.run(
            ["python3", "-c", source.replace("/tmp/q1x-review", str(root))],
            cwd=ROOT, check=False, capture_output=True, text=True,
            env={**os.environ, "GITHUB_REPOSITORY": "Quoralinex/goose", "PR_NUMBER": "7",
                 "EXPECTED_HEAD": "0123456789abcdef0123456789abcdef01234567",
                 "TRUSTED_REVIEWER_APP_ID": "1", "TRUSTED_REVIEWER_APP_SLUG": "q1x-reviewer"},
        )
        result_path = root / "semantic-review-result.json"
        return completed, json.loads(result_path.read_text()) if result_path.exists() else None


class Q1XSemanticAttestationResilienceTests(unittest.TestCase):
    def _attestation(self, stage, reviewer, **extra):
        payload = {
            "schema": "q1x.semantic-review-attestation.v2", "repository": "Quoralinex/goose",
            "pullRequestNumber": 7, "exactHead": "0123456789abcdef0123456789abcdef01234567",
            "stage": stage, "reviewer": reviewer, "surface": "ordinary-chat",
            "modelPolicy": "inherit-ordinary-chat-model", "capabilityClass": "deep", "effort": "high",
            "packetId": f"{stage}-packet", "evidenceDigest": "sha256:" + "1" * 64,
            "verdict": "pass", **extra,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        payload["attestationDigest"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
        return payload

    def _check(self, name, attestation, completed_at, check_id):
        return {"id": check_id, "name": name, "status": "completed", "conclusion": "success",
                "head_sha": "0123456789abcdef0123456789abcdef01234567", "completed_at": completed_at,
                "app": {"id": 1, "slug": "q1x-reviewer"},
                "output": {"summary": json.dumps(attestation)}}

    def _payload(self, goose_completed="2026-10-01T02:01:00Z", binding=None, goose_verdict="pass"):
        primary = self._attestation("ordinary-chat-primary", "ordinary-chat")
        goose = self._attestation(
            "goose-independent", "goose", advisoryId="advisory-1",
            runtimePin="ordinary-chat-inherited-deep",
            primaryAttestationDigest=binding or primary["attestationDigest"], verdict=goose_verdict,
        )
        return {"check_runs": [
            self._check("q1x/ordinary-chat-primary", primary, "2026-10-01T02:00:00Z", 1),
            self._check("q1x/goose-independent-review", goose, goose_completed, 2),
        ]}

    def _run_semantic_retry_loop(self, snapshots):
        marker = "          result_code=1\n          state='timeout-pending'\n          for attempt in $(seq 1 61); do"
        start = REVIEW.index(marker)
        end = REVIEW.index("\n          done", start) + len("\n          done")
        verifier = textwrap.dedent(extract_embedded_python("/tmp/q1x-review/verify_semantic_attestations.py"))
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "verify_semantic_attestations.py").write_text(verifier.replace("/tmp/q1x-review", temp_dir))
            for number, snapshot in enumerate(snapshots, 1):
                (root / f"snapshot-{number}.json").write_text(json.dumps(snapshot))
            loop = textwrap.dedent(REVIEW[start:end]).replace("/tmp/q1x-review", temp_dir)
            script = "\n".join([
                "set -euo pipefail",
                "collections=0",
                "verifications=0",
                'collect_check_runs() { collections=$((collections + 1)); cat "$Q1X_TEST_FIXTURE_DIR/snapshot-$collections.json"; }',
                "retry_semantic_collection_failure() { return 1; }",
                "sleep() { :; }",
                'python3() { verifications=$((verifications + 1)); command python3 "$@"; }',
                loop,
                'printf "%s %s %s %s\\n" "$collections" "$verifications" "$state" "$result_code" > "$Q1X_TEST_FIXTURE_DIR/metrics"',
            ])
            completed = subprocess.run(
                ["bash", "-c", script], cwd=ROOT, check=False, capture_output=True, text=True,
                env={**os.environ, "Q1X_TEST_FIXTURE_DIR": temp_dir,
                     "GITHUB_REPOSITORY": "Quoralinex/goose", "PR_NUMBER": "7",
                     "EXPECTED_HEAD": "0123456789abcdef0123456789abcdef01234567",
                     "TRUSTED_REVIEWER_APP_ID": "1", "TRUSTED_REVIEWER_APP_SLUG": "q1x-reviewer"},
            )
            metrics = (root / "metrics").read_text().split() if (root / "metrics").exists() else []
            result = json.loads((root / "semantic-review-result.json").read_text()) if (root / "semantic-review-result.json").exists() else None
            return completed, metrics, result

    def test_retry_loop_recollects_and_accepts_fresh_causal_attestation(self):
        completed, metrics, result = self._run_semantic_retry_loop([
            self._payload("2026-10-01T01:59:00Z"), self._payload(),
        ])
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(["2", "2", "completed-clean", "0"], metrics)
        self.assertEqual("completed-clean", result["state"])

    def test_retry_loop_stops_on_terminal_invalid_attestation(self):
        completed, metrics, result = self._run_semantic_retry_loop([
            self._payload("2026-10-01T01:59:00Z", goose_verdict="findings"), self._payload(),
        ])
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(["1", "1", "invalid-attestation", "1"], metrics)
        self.assertEqual("invalid-attestation", result["state"])

    def test_stale_goose_completion_is_retryable(self):
        completed, result = run_semantic_verifier(self._payload("2026-10-01T01:59:00Z"))
        self.assertEqual(2, completed.returncode, completed.stderr)
        self.assertEqual("causal-provenance-pending", result["state"])

    def test_superseded_primary_binding_is_retryable(self):
        earlier = self._attestation("ordinary-chat-primary", "ordinary-chat", packetId="earlier-primary")
        payload = self._payload(binding=earlier["attestationDigest"])
        payload["check_runs"].insert(0, self._check(
            "q1x/ordinary-chat-primary", earlier, "2026-10-01T01:58:00Z", 0,
        ))
        completed, result = run_semantic_verifier(payload)
        self.assertEqual(2, completed.returncode, completed.stderr)
        self.assertIn("binds the accepted primary", result["retryReason"])

    def test_unknown_primary_binding_is_terminal(self):
        completed, metrics, result = self._run_semantic_retry_loop([
            self._payload(binding="sha256:" + "2" * 64), self._payload(),
        ])
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(["1", "1", "invalid-attestation", "1"], metrics)
        self.assertIn("known superseded primary", result["error"])

    def test_nonpassing_older_primary_cannot_justify_retry(self):
        earlier = self._attestation(
            "ordinary-chat-primary", "ordinary-chat", packetId="earlier-primary", verdict="findings",
        )
        payload = self._payload(binding=earlier["attestationDigest"])
        payload["check_runs"].insert(0, self._check(
            "q1x/ordinary-chat-primary", earlier, "2026-10-01T01:58:00Z", 0,
        ))
        completed, result = run_semantic_verifier(payload)
        self.assertEqual(3, completed.returncode, completed.stderr)
        self.assertEqual("invalid-attestation", result["state"])

    def test_stale_goose_non_pass_verdict_remains_terminal(self):
        completed, result = run_semantic_verifier(
            self._payload("2026-10-01T01:59:00Z", goose_verdict="findings")
        )
        self.assertEqual(3, completed.returncode, completed.stderr)
        self.assertEqual("invalid-attestation", result["state"])

    def test_exhausted_causal_retry_is_labelled_timeout(self):
        marker = 'if [ "$state" = \'timeout-pending\' ] && [ -f /tmp/q1x-review/semantic-review-result.json ]'
        start = REVIEW.index(marker)
        end = REVIEW.index("            fi", start) + len("            fi")
        source = textwrap.dedent(REVIEW[start:end])
        with tempfile.TemporaryDirectory() as temp_dir:
            result_path = Path(temp_dir) / "semantic-review-result.json"
            for initial, expected in (
                ("causal-provenance-pending", "timeout-pending"),
                ("invalid-attestation", "invalid-attestation"),
            ):
                result_path.write_text(json.dumps({"state": initial, "retryReason": "prior causal mismatch"}))
                completed = subprocess.run(
                    ["bash", "-c", "set -euo pipefail\nstate=timeout-pending\n" + source.replace("/tmp/q1x-review", temp_dir)],
                    cwd=ROOT, check=False, capture_output=True, text=True,
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
                result = json.loads(result_path.read_text())
                self.assertEqual(expected, result["state"])
                self.assertEqual("prior causal mismatch", result["retryReason"])

    def test_malformed_binding_is_terminal(self):
        payload = self._payload(binding="invalid")
        goose_check = payload["check_runs"][1]
        goose = json.loads(goose_check["output"]["summary"])
        goose.pop("attestationDigest")
        encoded = json.dumps(goose, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        goose["attestationDigest"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
        goose_check["output"]["summary"] = json.dumps(goose)
        completed, result = run_semantic_verifier(payload)
        self.assertEqual(3, completed.returncode, completed.stderr)
        self.assertEqual("invalid-attestation", result["state"])

    def test_retryable_observation_preserves_prior_terminal_result(self):
        terminal = {"schema": "q1x.two-stage-semantic-review-result.v2",
                    "state": "invalid-attestation", "exactHead": "0123456789abcdef0123456789abcdef01234567",
                    "error": "prior terminal failure"}
        completed, result = run_semantic_verifier(self._payload("2026-10-01T01:59:00Z"), terminal)
        self.assertEqual(2, completed.returncode, completed.stderr)
        self.assertEqual(terminal, result)

    def _extract_shell_function(self, name):
        match = re.search(
            rf"          {re.escape(name)}\(\) \{{\n(?P<body>.*?)\n          \}}",
            REVIEW,
            re.DOTALL,
        )
        self.assertIsNotNone(match, f"{name} helper function is missing")
        return f"{name}() {{\n" + textwrap.dedent(match.group("body")) + "\n}"

    def test_transient_semantic_collection_failure_is_retryable(self):
        self.assertIn("for attempt in $(seq 1 61); do", REVIEW)
        self.assertIn('if ! collect_check_runs > "$semantic_check_runs_tmp"; then', REVIEW)
        self.assertIn('retry_semantic_collection_failure "check-runs" "$attempt"', REVIEW)
        self.assertIn('retry_semantic_collection_failure "check-runs-json" "$attempt"', REVIEW)
        self.assertIn(
            'mv "$semantic_check_runs_tmp" /tmp/q1x-review/semantic-check-runs.json',
            REVIEW,
        )

        retry_source = self._extract_shell_function("retry_semantic_collection_failure")
        script = "\n".join(
            [
                "set -euo pipefail",
                "sleep() { :; }",
                "write_semantic_collection_error_result() { :; }",
                retry_source,
                "attempts=0",
                "success=0",
                'source_cmd() { attempts=$((attempts + 1)); [ "$attempts" -gt 1 ]; }',
                "state=unknown",
                "result_code=0",
                "for attempt in 1 2; do",
                "  if ! source_cmd; then",
                '    if retry_semantic_collection_failure "check-runs" "$attempt"; then continue; else break; fi',
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

    def test_terminal_semantic_collection_failure_is_deterministic_and_fail_closed(self):
        write_source = self._extract_shell_function("write_semantic_collection_error_result")
        retry_source = self._extract_shell_function("retry_semantic_collection_failure")
        script = "\n".join(
            [
                "set -euo pipefail",
                "mkdir -p /tmp/q1x-review",
                "rm -f /tmp/q1x-review/semantic-review-result.json /tmp/q1x-review/semantic-review-result.tmp",
                "EXPECTED_HEAD=0123456789abcdef0123456789abcdef01234567",
                "state=unknown",
                "result_code=0",
                "sleep() { :; }",
                write_source,
                retry_source,
                "set +e",
                'retry_semantic_collection_failure "check-runs-json" 61',
                "terminal_code=$?",
                "set -e",
                'test "$terminal_code" -ne 0',
                'test "$state" = "collection-error"',
                'test "$result_code" -eq 1',
                "jq -e '.schema == \"q1x.two-stage-semantic-review-result.v2\" and .state == \"collection-error\" and .exactHead == \"0123456789abcdef0123456789abcdef01234567\" and .collectionError == \"check-runs-json\"' /tmp/q1x-review/semantic-review-result.json >/dev/null",
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


class Q1XAssuranceResilienceTests(unittest.TestCase):
    def test_transient_collection_and_classifier_failures_are_retryable(self):
        self.assertIn("for attempt in $(seq 1 46); do", REVIEW)
        self.assertIn('if ! collect_check_runs > "$check_runs_tmp"; then', REVIEW)
        self.assertIn('retry_collection_failure "check-runs" "$attempt"', REVIEW)
        self.assertRegex(
            REVIEW,
            r"if ! gh api --paginate --slurp -H 'Accept: application/vnd\.github\+json' \\\n"
            r'\s+"repos/\$GITHUB_REPOSITORY/commits/\$EXPECTED_HEAD/status\?per_page=100" \\\n'
            r"\s+\| jq '\{statuses: \[\.\[\]\.statuses\[\]\]\}' > \"\$status_tmp\"; then",
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
                        "grep -F 'status?per_page=100' .github/workflows/q1x-pr-review.yml >/dev/null",
                        "test \"$(grep -c 'gh api --paginate --slurp' .github/workflows/q1x-pr-review.yml)\" -ge 3",
                        "mkdir -p /tmp/q1x-review",
                        "printf '%s\\n' '{\"check_runs\":[{\"name\":\"security-old\"}]}' > /tmp/q1x-review/check-runs.json",
                        "printf '%s\\n' '{\"statuses\":[{\"context\":\"security-old\",\"state\":\"success\"}]}' > /tmp/q1x-review/status.json",
                        "terminal_called=0",
                        "write_collection_error_result() { terminal_called=$((terminal_called + 1)); }",
                        "state=unknown",
                        "result_code=0",
                        "set +e",
                        'retry_collection_failure "status" 46',
                        "terminal_code=$?",
                        "set -e",
                        'test "$terminal_code" -ne 0',
                        'test "$terminal_called" -eq 1',
                        'test "$state" = "collection-error"',
                        'test "$result_code" -eq 1',
                        "test ! -e /tmp/q1x-review/check-runs.json",
                        "test ! -e /tmp/q1x-review/status.json",
                        "write_collection_error_result() { :; }",
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

    def test_evidence_workflow_is_read_only_and_sha_pinned(self):
        caller = (ROOT / ".github/workflows/q1x-goose-review.yml").read_text()
        # This workflow publishes no merge decision and holds read-only GitHub
        # permissions. A historical merge-authority test must not invent write
        # authority or a pull_request_target requirement for this evidence job.
        self.assertIn("\n  pull_request:\n", caller)
        readonly_permissions(caller)
        readonly_permissions(REVIEW)
        self.assertIn("\n  actions: read\n", caller)
        self.assertIn("\n      actions: read\n", REVIEW)
        caller_block = re.search(r"(?m)^permissions:\n((?:  [a-z-]+: read\n)+)", caller)
        called_block = re.search(r"(?m)^    permissions:\n((?:      [a-z-]+: read\n)+)", REVIEW)
        self.assertIsNotNone(caller_block)
        self.assertIsNotNone(called_block)
        caller_scopes = set(re.findall(r"(?m)^  ([a-z-]+): read$", caller_block.group(1)))
        called_scopes = set(re.findall(r"(?m)^      ([a-z-]+): read$", called_block.group(1)))
        self.assertTrue(called_scopes <= caller_scopes,
                        f"called workflow requests scopes absent from caller: {called_scopes - caller_scopes}")
        self.assertNotIn("gh pr merge", REVIEW)
        match = re.search(
            r"uses:\s+Quoralinex/goose/\.github/workflows/q1x-pr-review\.yml@([0-9a-f]{40})",
            caller,
        )
        self.assertIsNotNone(match, "reusable evidence workflow must use an immutable SHA")
        pinned = self._read_pinned_workflow(match.group(1))
        self.assertEqual(REVIEW, pinned)
        self.assertNotIn("uses: ./.github/workflows/q1x-pr-review.yml", caller)


def readonly_permissions(workflow):
    """Validate every explicit top-level/job permission block, conservatively.

    The supported subset is read-all, {}, or block mappings of read/none.
    Expressions, YAML aliases/merges and nonempty flow mappings are refused so
    an unevaluated value cannot silently grant write authority.
    """
    lines = workflow.splitlines()
    headers = []
    for index, line in enumerate(lines):
        match = re.fullmatch(r"( *)(?:permissions|'permissions'|\"permissions\")\s*:\s*([^#]*)(?:#.*)?", line)
        if match: headers.append((index, len(match.group(1)), match.group(2).strip()))
    if not headers: raise ValueError("Explicit read-only permissions are required")
    for index, indent, value in headers:
        if value in ["read-all", "'read-all'", '\"read-all\"', "{}"]: continue
        if value: raise ValueError("Unsupported or writable permissions value")
        mapping_indent = None
        for child in lines[index + 1:]:
            if not child.strip() or child.lstrip().startswith('#'): continue
            depth = len(child) - len(child.lstrip(' '))
            if depth <= indent: break
            if mapping_indent is None: mapping_indent = depth
            if depth != mapping_indent or not re.fullmatch(
                r" *(?:[A-Za-z0-9_-]+|'[A-Za-z0-9_-]+'|\"[A-Za-z0-9_-]+\")\s*:\s*(?:read|none|'read'|'none'|\"read\"|\"none\")\s*(?:#.*)?", child
            ): raise ValueError("Unsupported or writable permission scope")
        if mapping_indent is None: raise ValueError("Empty implicit permission block")


class Q1XReadonlyPermissionsTests(unittest.TestCase):
    def test_rejects_every_scope_and_write_all(self):
        for source in [
            "permissions: write-all\n", "permissions: 'write-all' # unsafe\n",
            "permissions:\n  issues: write # unsafe\n", "permissions:\n  id-token: write\n",
            "permissions:\n  attestations: write\n", 'permissions:\n  "checks": "write"\n',
            "permissions: {issues: write}\n", "permissions: ${{ inputs.permissions }}\n",
            "permissions: &allow {contents: write}\n", "permissions: *allow\n",
            "permissions:\n  <<: *allow\n", "name: implicit default permissions\n",
        ]:
            with self.subTest(source=source):
                with self.assertRaises(ValueError): readonly_permissions(source)

    def test_accepts_explicit_read_and_none_mappings(self):
        for source in [
            "permissions: read-all\n", "permissions: {}\n",
            "permissions:\n  contents: read # checkout\n  issues: none\n",
            "permissions:\n  'contents': 'read'\njobs:\n  verify:\n    permissions:\n      checks: read\n",
        ]:
            with self.subTest(source=source): readonly_permissions(source)

    def test_rejects_write_in_job_override(self):
        with self.assertRaises(ValueError):
            readonly_permissions("permissions: read-all\njobs:\n  verify:\n    permissions:\n      packages: write # elevation\n")


class Q1XLiveProviderScopeTests(unittest.TestCase):
    def test_q1x_security_tests_do_not_trigger_live_provider_credentials(self):
        smoke = (ROOT / ".github/workflows/pr-smoke-test.yml").read_text()
        self.assertIn("              - '!tests/q1x/**'", smoke)
        validate = (ROOT / ".github/workflows/q1x-agent-plugin-validate.yml").read_text()
        self.assertIn("      - '.github/workflows/pr-smoke-test.yml'", validate)


if __name__ == "__main__":
    unittest.main()
