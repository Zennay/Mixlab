"""Source-bound, fail-closed CI provenance for the ML-07 repeatability gate.

No audio, external networking, CI credentials, or workflow dispatch occurs here.
The test checks the exact workflow that performs private PCM source admission.
"""
import re
from pathlib import Path
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ml07-repeatability.yml"
CHECKOUT_SHA = "11d5960a326750d5838078e36cf38b85af677262"
PYTHON_SHA = "a26af69be951a213d495a4c3e4e4022e16d87065"
TRUSTED_PR_HEAD = "${{ github.event.pull_request.head.sha || github.sha }}"


def admit_workflow(source: str) -> None:
    # Only these two immutable action definitions may prepare the execution
    # context. Never accept floating refs, duplicate steps, or SHA substrings
    # buried in comments/environment/example text.
    uses = re.findall(r"^\s+uses:\s*(\S+)", source, re.MULTILINE)
    assert uses == [
        f"actions/checkout@{CHECKOUT_SHA}",
        f"actions/setup-python@{PYTHON_SHA}",
    ], "action refs must be exact reviewed commits"
    assert re.search(
        r"^\s+ref:\s*" + re.escape(TRUSTED_PR_HEAD) + r"\s*$",
        source, re.MULTILINE
    ), "checkout ref must bind to PR HEAD"
    assert re.search(
        r"^\s+EXPECTED:\s*" + re.escape(TRUSTED_PR_HEAD) + r"\s*$",
        source, re.MULTILINE
    ), "expected source must derive from the trusted event"
    assert 'test "$(git rev-parse HEAD)" = "$EXPECTED"' in source, (
        "runtime git HEAD must actually be verified"
    )
    assert "persist-credentials: false" in source, (
        "no persistent checkout token may remain in the workspace"
    )
    assert re.search(r"^permissions:\s*\n\s+contents:\s*read\s*$", source, re.MULTILINE), (
        "workflow token must stay read-only"
    )


class RepeatabilityWorkflowProvenanceTests(unittest.TestCase):
    def test_immutable_source_actions_and_runtime_identity(self):
        admit_workflow(WORKFLOW.read_text(encoding="utf-8"))

    def test_action_tag_and_foreign_sha_mutations_fail(self):
        original = WORKFLOW.read_text(encoding="utf-8")
        for original_ref, mutated_ref in (
            (f"actions/checkout@{CHECKOUT_SHA}", "actions/checkout@v4"),
            (f"actions/setup-python@{PYTHON_SHA}", "actions/setup-python@v5"),
            (f"actions/checkout@{CHECKOUT_SHA}", "actions/checkout@" + "a" * 40),
        ):
            with self.subTest(mutated_ref=mutated_ref):
                changed = original.replace(original_ref, mutated_ref, 1)
                self.assertNotEqual(changed, original)
                with self.assertRaises(AssertionError):
                    admit_workflow(changed)

    def test_untrusted_head_and_removed_runtime_identity_fail(self):
        original = WORKFLOW.read_text(encoding="utf-8")
        for old, new in (
            ("ref: " + TRUSTED_PR_HEAD, "ref: main"),
            ("EXPECTED: " + TRUSTED_PR_HEAD, "EXPECTED: ${{ github.sha }}"),
            ('test "$(git rev-parse HEAD)" = "$EXPECTED"', 'echo "verified"'),
            ("persist-credentials: false", "persist-credentials: true"),
            ("contents: read", "contents: write"),
        ):
            with self.subTest(mutated=new):
                changed = original.replace(old, new, 1)
                self.assertNotEqual(changed, original)
                with self.assertRaises(AssertionError):
                    admit_workflow(changed)


if __name__ == "__main__":
    unittest.main()
