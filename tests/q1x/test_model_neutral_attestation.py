"""Execute the shipped workflow verifier against isolated exact-head fixtures."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github/workflows/q1x-pr-review.yml'
HEAD = 'a' * 40
REPO = 'Quoralinex/commissioning-fixture'

def seal(value):
    value.pop('attestationDigest', None)
    value['attestationDigest'] = 'sha256:' + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    ).hexdigest()
    return value

def attestation(stage, version=2):
    value = {
        'schema': f'q1x.semantic-review-attestation.v{version}',
        'repository': REPO, 'pullRequestNumber': 7, 'exactHead': HEAD,
        'stage': stage, 'reviewer': 'ordinary-chat' if stage == 'ordinary-chat-primary' else 'goose',
        'surface': 'ordinary-chat', 'effort': 'high', 'packetId': f'fixture-{stage}',
        'evidenceDigest': 'sha256:' + 'b' * 64, 'verdict': 'pass',
    }
    if version == 1:
        value['model'] = 'gpt-5.6'
    else:
        value.update(modelPolicy='inherit-ordinary-chat-model', capabilityClass='deep')
    if stage == 'goose-independent':
        value.update(advisoryId='fixture-independent', runtimePin='ordinary-chat:inherited-model:high')
    return seal(value)

class ModelNeutralAttestationTests(unittest.TestCase):
    def checks(self, primary_version=2, goose_version=2):
        primary = attestation('ordinary-chat-primary', primary_version)
        goose = attestation('goose-independent', goose_version)
        goose['primaryAttestationDigest'] = primary['attestationDigest']
        seal(goose)
        return [dict(id=i+1, name=name, status='completed', conclusion='success', head_sha=HEAD,
                     app={'id': 123, 'slug': 'fixture-reviewer'}, completed_at=f'2026-10-28T00:00:0{i+1}Z',
                     output={'summary': json.dumps(att)})
                for i, (name, att) in enumerate([
                    ('q1x/ordinary-chat-primary', primary), ('q1x/goose-independent-review', goose)])]

    def run_verifier(self, checks):
        workflow = WORKFLOW.read_text()
        match = re.search(r"cat > /tmp/q1x-review/verify_semantic_attestations.py <<'PY'\n(.*?)\n          PY", workflow, re.S)
        self.assertIsNotNone(match)
        with tempfile.TemporaryDirectory(prefix='q1x-attestation-test-') as tmp:
            script = textwrap.dedent(match.group(1)).replace('/tmp/q1x-review/', tmp + '/')
            Path(tmp, 'semantic-check-runs.json').write_text(json.dumps({'check_runs': checks}))
            env = {**os.environ, 'GITHUB_REPOSITORY': REPO, 'PR_NUMBER': '7', 'EXPECTED_HEAD': HEAD,
                   'TRUSTED_REVIEWER_APP_ID': '123', 'TRUSTED_REVIEWER_APP_SLUG': 'fixture-reviewer'}
            result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True, timeout=10)
            return result.returncode, result.stderr

    def test_accepts_model_neutral_v2(self):
        self.assertEqual((0, ''), self.run_verifier(self.checks()))

    def test_preserves_immutable_v1_compatibility(self):
        self.assertEqual((0, ''), self.run_verifier(self.checks(1, 1)))

    def test_accepts_digest_bound_migration_from_v1_primary_to_v2_goose(self):
        self.assertEqual((0, ''), self.run_verifier(self.checks(1, 2)))

    def test_rejects_invalid_or_ambiguous_model_policy(self):
        for changes in [
            {'modelPolicy': 'arbitrary-provider'}, {'capabilityClass': 'light'},
            {'model': 'gpt-6'}, {'schema': 'q1x.semantic-review-attestation.v99'},
        ]:
            with self.subTest(changes=changes):
                checks = self.checks()
                value = json.loads(checks[1]['output']['summary']); value.update(changes)
                checks[1]['output']['summary'] = json.dumps(seal(value))
                self.assertNotEqual(0, self.run_verifier(checks)[0])

    def test_legacy_schema_cannot_claim_new_policy_or_wrong_model(self):
        for changes in [{'model': 'gpt-6'}, {'modelPolicy': 'inherit-ordinary-chat-model'}, {'capabilityClass': 'deep'}]:
            with self.subTest(changes=changes):
                checks = self.checks(1, 1)
                value = json.loads(checks[1]['output']['summary']); value.update(changes)
                checks[1]['output']['summary'] = json.dumps(seal(value))
                self.assertNotEqual(0, self.run_verifier(checks)[0])

    def test_v2_preserves_authority_and_exact_head_guards(self):
        for field, value in [('surface','work-chat'), ('exactHead','c'*40), ('repository','other/repo'),
                             ('pullRequestNumber',8), ('reviewer','codex'), ('verdict','abstain'),
                             ('primaryAttestationDigest','sha256:'+'0'*64), ('runtimePin','')]:
            with self.subTest(field=field):
                checks = self.checks()
                att = json.loads(checks[1]['output']['summary']); att[field] = value
                checks[1]['output']['summary'] = json.dumps(seal(att))
                self.assertNotEqual(0, self.run_verifier(checks)[0])

    def test_rejects_untrusted_publisher_tampering_and_reversed_order(self):
        for mutation in ['publisher', 'digest', 'order', 'missing']:
            with self.subTest(mutation=mutation):
                checks = self.checks()
                if mutation == 'publisher': checks[1]['app']['id'] = 999
                elif mutation == 'order': checks[1]['completed_at'] = checks[0]['completed_at']
                elif mutation == 'missing': checks.pop()
                else:
                    att = json.loads(checks[1]['output']['summary']); att['packetId'] = 'tampered'
                    checks[1]['output']['summary'] = json.dumps(att)
                self.assertNotEqual(0, self.run_verifier(checks)[0])

if __name__ == '__main__':
    unittest.main()
