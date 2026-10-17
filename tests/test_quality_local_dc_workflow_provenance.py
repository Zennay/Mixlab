"""Immutable source receipt for MixLab local DC quality CI.

This test is deliberately offline and checks the executable workflow fields,
not upstream content or a public music/audio artifact.
"""
import re
import unittest
from pathlib import Path

WORKFLOW = (Path(__file__).resolve().parents[1]
            / ".github/workflows/ml07-local-dc.yml")
CHECKOUT = "11d5960a326750d5838078e36cf38b85af677262"
PYTHON = "ece7cb06caefa5fff74198d8649806c4678c61a1"
HEAD = "${{ github.event.pull_request.head.sha || github.sha }}"


def assert_accepted(source: str):
    uses = re.findall(r"^\s+-?\s*uses:\s*(\S+)", source, re.M)
    assert uses == [
        f"actions/checkout@{CHECKOUT}",
        f"actions/checkout@{CHECKOUT}",
        f"actions/setup-python@{PYTHON}",
    ], "workflow actions must use exact reviewed commits"
    assert len(re.findall(r"^\s+ref:\s*" + re.escape(HEAD) + r"\s*$", source, re.M)) == 2, (
        "both quality jobs must test event-bound source HEAD"
    )
    assert len(re.findall(r"^\s+EXPECTED_SHA:\s*" + re.escape(HEAD) + r"\s*$", source, re.M)) == 2, (
        "both quality jobs must supply a trusted expected SHA"
    )
    assert source.count('test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"') == 2, (
        "both quality jobs must actually verify checked out HEAD"
    )
    assert source.count("persist-credentials: false") == 2, (
        "both checkouts must not persist credentials"
    )
    assert re.search(r"(?m)^permissions:\s*\n\s+contents:\s*read\s*$", source), (
        "permissions must stay read-only"
    )
    assert len(re.findall(r"^\s+runs-on:\s*ubuntu-latest\s*$", source, re.M)) == 2, (
        "both quality jobs must remain hosted"
    )


class SourceBoundDCWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_uses_immutable_verifiable_actions(self):
        assert_accepted(self.source)

    def test_floating_or_foreign_actions_rejected(self):
        for old, new in (
            (f"checkout@{CHECKOUT}", "checkout@v4"),
            (f"setup-python@{PYTHON}", "setup-python@v6"),
            (f"checkout@{CHECKOUT}", "checkout@" + "a" * 40),
        ):
            with self.subTest(replacement=new):
                changed = self.source.replace(old, new, 1)
                self.assertNotEqual(changed, self.source)
                with self.assertRaises(AssertionError):
                    assert_accepted(changed)

    def test_source_identity_and_permission_mutations_rejected(self):
        for old, new in (
            ("ref: " + HEAD, "ref: main"),
            ("EXPECTED_SHA: " + HEAD, "EXPECTED_SHA: ${{ github.sha }}"),
            ('test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"', 'echo "passed"'),
            ("persist-credentials: false", "persist-credentials: true"),
            ("contents: read", "contents: write"),
            ("runs-on: ubuntu-latest", "runs-on: self-hosted"),
        ):
            with self.subTest(replacement=new):
                changed = self.source.replace(old, new, 1)
                self.assertNotEqual(changed, self.source)
                with self.assertRaises(AssertionError):
                    assert_accepted(changed)


if __name__ == "__main__":
    unittest.main()
