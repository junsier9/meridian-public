from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.test_helpers import ROOT

import sys

SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.evidence_contracts import required_source_commit_sha, with_evidence_metadata
from scripts.verify import run_evidence_freshness_contract as freshness


CONTRACT_PATH = ROOT / "config" / "agent_layer_governance" / "evidence_freshness_contract.json"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


class EvidenceContractTests(unittest.TestCase):
    def test_with_evidence_metadata_adds_standard_fields(self) -> None:
        with mock.patch.dict(os.environ, {"SOURCE_COMMIT_SHA": "abc123", "GITHUB_SHA": ""}, clear=False):
            payload = with_evidence_metadata(
                {"generated_at_utc": "2026-04-20T10:00:00Z", "status": "passed"},
                evidence_family="real_shadow_verify",
                contract_version="real_shadow_verify.v1",
                repo_root=ROOT,
            )

        self.assertEqual(payload["produced_at_utc"], "2026-04-20T10:00:00Z")
        self.assertEqual(payload["source_commit_sha"], "abc123")
        self.assertEqual(payload["evidence_family"], "real_shadow_verify")
        self.assertEqual(payload["contract_version"], "real_shadow_verify.v1")

    def test_required_source_commit_sha_fails_closed_when_no_commit_source_exists(self) -> None:
        with mock.patch.dict(os.environ, {"SOURCE_COMMIT_SHA": "", "GITHUB_SHA": ""}, clear=False):
            with mock.patch("enhengclaw.ops.evidence_contracts.subprocess.run") as run_mock:
                run_mock.return_value = mock.Mock(returncode=1, stdout="", stderr="fatal")
                with self.assertRaisesRegex(RuntimeError, "source_commit_sha is required"):
                    required_source_commit_sha(repo_root=ROOT)

    def test_extract_project_state_evidence_references_reads_backticked_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="evidence_contract_refs_") as tmpdir:
            project_state = Path(tmpdir) / "PROJECT_STATE.md"
            project_state.write_text(
                "\n".join(
                    [
                        "# PROJECT_STATE.md",
                        "",
                        "## Current Accepted Evidence",
                        "- one:",
                        "  - `%LOCALAPPDATA%\\EnhengClaw\\one\\bundle_summary.json`",
                        "- two:",
                        "  - `artifacts\\real_shadow_acceptance\\verify_runs\\demo\\verify_summary.json`",
                    ]
                ),
                encoding="utf-8",
            )

            references = freshness.extract_project_state_evidence_references(project_state)

        self.assertEqual(
            references,
            [
                "%LOCALAPPDATA%\\EnhengClaw\\one\\bundle_summary.json",
                "artifacts\\real_shadow_acceptance\\verify_runs\\demo\\verify_summary.json",
            ],
        )

    def test_project_state_evidence_freshness_passes_for_fresh_matching_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="evidence_contract_pass_") as tmpdir:
            localappdata = Path(tmpdir) / "localappdata"
            bundle_path = (
                localappdata
                / "EnhengClaw"
                / "openclaw_live_market_observer"
                / "retained"
                / "direct_bundle_env_unified"
                / "bundle_summary.json"
            )
            _write_json(
                bundle_path,
                {
                    "produced_at_utc": "2026-04-20T10:00:00Z",
                    "source_commit_sha": "abc123",
                    "evidence_family": "openclaw_deployment_gate",
                    "contract_version": "openclaw_deployment_gate.v1",
                    "status": "success",
                },
            )
            project_state = Path(tmpdir) / "PROJECT_STATE.md"
            project_state.write_text(
                "\n".join(
                    [
                        "# PROJECT_STATE.md",
                        "",
                        "## Current Accepted Evidence",
                        "- Latest successful direct clean-session OpenClaw deployment gate bundle:",
                        "  - `%LOCALAPPDATA%\\EnhengClaw\\openclaw_live_market_observer\\retained\\direct_bundle_env_unified\\bundle_summary.json`",
                    ]
                ),
                encoding="utf-8",
            )

            summary = freshness.evaluate_project_state_evidence_freshness(
                project_state_path=project_state,
                contract_path=CONTRACT_PATH,
                current_commit_sha="abc123",
                now_utc="2026-04-20T12:00:00Z",
                env={"LOCALAPPDATA": str(localappdata)},
            )

        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["references"][0]["status"], "passed")
        self.assertEqual(summary["references"][0]["evidence_family"], "openclaw_deployment_gate")

    def test_project_state_evidence_freshness_fails_for_stale_or_mismatched_commit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="evidence_contract_fail_") as tmpdir:
            verify_path = (
                Path(tmpdir)
                / "artifacts"
                / "real_shadow_acceptance"
                / "verify_runs"
                / "demo"
                / "verify_summary.json"
            )
            _write_json(
                verify_path,
                {
                    "produced_at_utc": "2026-04-10T10:00:00Z",
                    "source_commit_sha": "oldsha",
                    "evidence_family": "real_shadow_verify",
                    "contract_version": "real_shadow_verify.v1",
                    "status": "passed",
                },
            )
            project_state = Path(tmpdir) / "PROJECT_STATE.md"
            project_state.write_text(
                "\n".join(
                    [
                        "# PROJECT_STATE.md",
                        "",
                        "## Current Accepted Evidence",
                        f"- `{verify_path}`",
                    ]
                ),
                encoding="utf-8",
            )

            summary = freshness.evaluate_project_state_evidence_freshness(
                project_state_path=project_state,
                contract_path=CONTRACT_PATH,
                current_commit_sha="abc123",
                now_utc="2026-04-20T12:00:00Z",
            )

        self.assertEqual(summary["status"], "failed")
        blockers = summary["references"][0]["blockers"]
        self.assertTrue(any("evidence is stale" in blocker for blocker in blockers))
        self.assertTrue(any("source_commit_sha mismatch" in blocker for blocker in blockers))


if __name__ == "__main__":
    unittest.main()
