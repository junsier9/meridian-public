from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_helpers import ROOT

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enhengclaw.core.execution_control import TRUST_ROOT_DIR_ENV
from enhengclaw.integrations.openclaw.market_observer import governed_runtime_session_path
from scripts.openclaw import _market_observer_live_inputs as live_inputs
from scripts.openclaw import _research_workbench_inputs as research_inputs
from scripts.openclaw import run_openclaw_research_cycle as research_cycle


def _unlock_trust_root(summary: dict[str, object]) -> None:
    trust_root_dir = Path(str(summary["trust_root_dir"]))
    allowed_signers_path = Path(str(summary["allowed_signers_path"]))
    if trust_root_dir.exists():
        live_inputs.unlock_trust_root_for_publication(trust_root_dir, allowed_signers_path)


def _lane_success_response(request_payload: dict[str, object], *, lane_id: str, request_path: Path) -> dict[str, object]:
    final_output_path = request_path.with_suffix(".final.json")
    runtime_session_path = request_path.with_suffix(".runtime.json")
    _write_any_path_text(final_output_path, "{}")
    _write_any_path_text(runtime_session_path, "{}")
    return {
        "contract_version": request_payload["contract_version"],
        "status": "success",
        "execution_status": "success",
        "run_state": "FINALIZED",
        "owner_run_id": f"{lane_id}:owner-run",
        "spec_version": 1,
        "final_output_path": str(final_output_path),
        "runtime_session_path": str(runtime_session_path),
        "compiler_artifact_paths": [str(request_path.with_suffix(".compiler.json"))],
        "accepted_signal_ids": [f"{lane_id}:signal:1"],
        "blocked_reason": None,
        "quarantine_reason": None,
        "error": None,
        "artifacts_root": request_payload.get("artifacts_root"),
    }


def _write_any_path_text(path: Path, content: str) -> None:
    normalized = os.path.abspath(os.path.normpath(str(path)))
    if os.name == "nt" and not normalized.startswith("\\\\?\\"):
        if normalized.startswith("\\\\"):
            normalized = "\\\\?\\UNC\\" + normalized[2:]
        else:
            normalized = "\\\\?\\" + normalized
    os.makedirs(os.path.dirname(normalized), exist_ok=True)
    with open(normalized, "w", encoding="utf-8") as handle:
        handle.write(content)


def _read_any_path_text(path: Path) -> str:
    normalized = os.path.abspath(os.path.normpath(str(path)))
    if os.name == "nt" and not normalized.startswith("\\\\?\\"):
        if normalized.startswith("\\\\"):
            normalized = "\\\\?\\UNC\\" + normalized[2:]
        else:
            normalized = "\\\\?\\" + normalized
    with open(normalized, "r", encoding="utf-8") as handle:
        return handle.read()


def _remove_any_path_tree(path: Path) -> None:
    normalized = os.path.abspath(os.path.normpath(str(path)))
    if os.name == "nt" and not normalized.startswith("\\\\?\\"):
        if normalized.startswith("\\\\"):
            normalized = "\\\\?\\UNC\\" + normalized[2:]
        else:
            normalized = "\\\\?\\" + normalized
    if not os.path.exists(normalized):
        return
    if os.name != "nt":
        shutil.rmtree(normalized, ignore_errors=True)
        return
    for dirpath, dirnames, filenames in os.walk(normalized, topdown=False):
        for filename in filenames:
            os.remove(os.path.join(dirpath, filename))
        for dirname in dirnames:
            os.rmdir(os.path.join(dirpath, dirname))
    os.rmdir(normalized)


class ResearchWorkbenchInputsTests(unittest.TestCase):
    def test_provisioning_creates_research_root_artifacts_and_summary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_research_inputs_") as tmpdir:
            external_root = Path(tmpdir) / "external"
            trust_root_dir = Path(tmpdir) / "programdata" / "EnhengClaw" / "trust"
            summary = research_inputs.provision_openclaw_research_inputs(
                external_root=external_root,
                trust_root_dir=trust_root_dir,
            )
            try:
                self.assertEqual(summary["status"], "success")
                self.assertEqual(summary["workflow"], "scheduled_research")
                self.assertEqual(summary["trust_root_mode"], "explicit_trust_root")
                self.assertTrue(summary["trust_root_override_applied"])
                self.assertTrue((external_root / "signer" / "execution_signer").exists())
                self.assertTrue((external_root / "permit" / "owner_review.json").exists())
                self.assertTrue((external_root / "permit" / "batch_approval.json").exists())
                self.assertTrue((external_root / "permit" / "execution_permit.json").exists())
                self.assertTrue((trust_root_dir / "allowed_signers").exists())
                self.assertTrue((external_root / "provision_summary.json").exists())
            finally:
                _unlock_trust_root(summary)

    def test_research_operator_env_accepts_dedicated_keys_for_research_lanes_only(self) -> None:
        env = {
            "ENHENGCLAW_MARKET_OBSERVER_MODEL_BASE_URL": "https://api.openai.com/v1",
            "ENHENGCLAW_MARKET_OBSERVER_MODEL_NAME": "gpt-5.4",
            "ENHENGCLAW_MARKET_OBSERVER_API_KEY": "market-key",
            "ENHENGCLAW_EVIDENCE_AGENT_MODEL_BASE_URL": "https://api.openai.com/v1",
            "ENHENGCLAW_EVIDENCE_AGENT_MODEL_NAME": "gpt-5.4",
            "ENHENGCLAW_EVIDENCE_AGENT_API_KEY": "evidence-key",
            "ENHENGCLAW_RISK_SIGNAL_AGENT_MODEL_BASE_URL": "https://api.openai.com/v1",
            "ENHENGCLAW_RISK_SIGNAL_AGENT_MODEL_NAME": "gpt-5.4",
            "ENHENGCLAW_RISK_SIGNAL_AGENT_API_KEY": "risk-key",
            "ENHENGCLAW_RESEARCH_SYNTHESIZER_MODEL_BASE_URL": "https://api.openai.com/v1",
            "ENHENGCLAW_RESEARCH_SYNTHESIZER_MODEL_NAME": "gpt-5.4",
            "ENHENGCLAW_RESEARCH_SYNTHESIZER_API_KEY": "synth-key",
            "ENHENGCLAW_RESEARCH_LEAD_MODEL_BASE_URL": "https://api.openai.com/v1",
            "ENHENGCLAW_RESEARCH_LEAD_MODEL_NAME": "gpt-5.4",
            "ENHENGCLAW_RESEARCH_LEAD_API_KEY": "lead-key",
        }
        resolved_env, meta = research_inputs.resolve_openclaw_research_operator_env(env)
        self.assertEqual(resolved_env["ENHENGCLAW_MARKET_OBSERVER_API_KEY"], "market-key")
        self.assertEqual(meta["workflow"], "scheduled_research")
        self.assertEqual(meta["missing_api_key_envs_by_lane"], {})
        self.assertFalse(meta["openclaw_mapping_used_by_lane"]["market_observer"])
        self.assertFalse(meta["openclaw_mapping_used_by_lane"]["research_lead"])


class OpenClawResearchCycleTests(unittest.TestCase):
    def _symbol_catalog(self) -> dict[str, object]:
        symbols = ("SOLUSDT", "BTCUSDT", "ETHUSDT", "SUIUSDT", "JTOUSDT", "ARBUSDT")
        return {
            "markets": {
                "spot": {"symbols": {symbol: {"symbol": symbol} for symbol in symbols}},
                "usdm_perp": {"symbols": {symbol: {"symbol": symbol} for symbol in symbols}},
            }
        }

    def _build_ohlcv_context(self, *, market_symbols: dict[str, object], scope: str, **_: object) -> dict[str, object]:
        markets: dict[str, object] = {}
        for market_type, key in (("spot", "spot_symbol"), ("usdm_perp", "usdm_symbol")):
            symbol = market_symbols.get(key)
            if symbol:
                markets[market_type] = {
                    "market_type": market_type,
                    "symbol": symbol,
                    "status": "full",
                    "intervals": {
                        interval: {
                            "interval": interval,
                            "bar_count": 256,
                            "coverage_days": 365.0,
                            "ready": True,
                            "last_open_time_utc": "2026-04-20T00:00:00Z",
                            "last_close_time_utc": "2026-04-20T01:00:00Z",
                            "last_close": "1.00000000",
                            "distance_to_high_pct": {"20": -1.0, "60": -2.0, "120": -3.0},
                            "distance_to_low_pct": {"20": 1.0, "60": 2.0, "120": 3.0},
                            "relative_volume_20": 1.1,
                            "realized_volatility_20": 0.02,
                        }
                        for interval in ("1h", "4h", "1d")
                    },
                    "breakout_samples_1d": [
                        {
                            "breakout_open_time_utc": "2026-04-10T00:00:00Z",
                            "forward_5d_return_pct": 6.2,
                            "max_drawdown_10d_pct": -3.1,
                        }
                    ],
                    "breakout_comparison_ready": True,
                }
        context = {
            "generated_at_utc": "2026-04-20T00:00:00Z",
            "exchange": "binance",
            "scope": scope,
            "market_symbols": {
                "spot_symbol": market_symbols.get("spot_symbol"),
                "usdm_symbol": market_symbols.get("usdm_symbol"),
            },
            "history_coverage": {
                "status": "full",
                "scope": scope,
                "markets": {
                    market_type: {
                        "symbol": entry["symbol"],
                        "status": "full",
                        "intervals": {
                            interval: {"bars": 256, "coverage_days": 365.0, "ready": True}
                            for interval in ("1h", "4h", "1d")
                        },
                    }
                    for market_type, entry in markets.items()
                },
                "breakout_comparison_ready": True,
            },
            "markets": markets,
            "summary_text": "history_coverage_status=full\nbreakout_comparison_ready=True",
        }
        return context

    def _write_snapshot(self, root: Path, payload: dict[str, object]) -> Path:
        snapshot_path = root / "snapshot.json"
        snapshot_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return snapshot_path

    def _lane_subprocess_side_effect(self, recorded_calls: list[tuple[str, dict[str, object], dict[str, str]]]):
        def side_effect(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            module_name = str(command[2])
            request_path = Path(str(command[4]))
            response_path = Path(str(command[6]))
            request_payload = json.loads(_read_any_path_text(request_path))
            env = _["env"] if "env" in _ else {}
            recorded_calls.append((module_name, request_payload, dict(env)))
            lane_id = module_name.rsplit(".", 1)[-1]
            response_payload = _lane_success_response(request_payload, lane_id=lane_id, request_path=request_path)
            _write_any_path_text(response_path, json.dumps(response_payload, indent=2, sort_keys=True))
            return subprocess.CompletedProcess(command, 0, stdout=f"{lane_id} ok", stderr="")

        return side_effect

    def test_first_cycle_creates_then_runs_four_resume_only_lanes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_research_cycle_") as tmpdir:
            root = Path(tmpdir)
            snapshot_path = self._write_snapshot(
                root,
                {
                    "cycle_id": "cycle-001",
                    "cycle_date": "2026-04-19",
                    "object_id": "sol-breakout-20260419",
                    "subject": "SOL",
                    "scope": "spot+perp",
                    "strategy_profile": "balanced",
                    "asset_bucket": "large_cap",
                    "observation": "SOL is still holding above the prior breakout area.",
                    "evidence": "Funding stayed controlled and volume expanded on the rebound.",
                    "risk": "Loss of the breakout shelf would invalidate the setup.",
                    "next_step": "Check whether strength persists into the next US session.",
                },
            )
            workbench_root = root / "workbench"
            provision_summary = {
                "summary_path": str(root / "external" / "provision_summary.json"),
                "permit_path": str(root / "external" / "permit" / "execution_permit.json"),
                "trust_root_dir": str(root / "programdata" / "EnhengClaw" / "trust"),
                "external_root": str(root / "external"),
            }
            recorded_calls: list[tuple[str, dict[str, object], dict[str, str]]] = []

            with patch.object(research_cycle, "provision_openclaw_research_inputs", return_value=provision_summary), patch.object(
                research_cycle,
                "resolve_openclaw_research_operator_env",
                return_value=({"OPENCLAW": "openclaw-secret"}, {"live_env_mode": "unified_openclaw_baseline", "openclaw_mapping_used_by_lane": {}}),
            ), patch.object(research_cycle, "load_symbol_catalog", return_value=self._symbol_catalog()), patch.object(
                research_cycle,
                "build_ohlcv_context",
                side_effect=self._build_ohlcv_context,
            ), patch.object(research_cycle.subprocess, "run", side_effect=self._lane_subprocess_side_effect(recorded_calls)):
                result = research_cycle.run_openclaw_research_cycle(
                    snapshot_path=snapshot_path,
                    workbench_root=workbench_root,
                    compiler_backend="live",
                )

            self.assertEqual(result["status"], "success")
            self.assertTrue(result["created_new_object"])
            self.assertEqual(
                [Path(module).name for module, _, _ in recorded_calls],
                [
                    "enhengclaw.integrations.openclaw.market_observer",
                    "enhengclaw.integrations.openclaw.evidence_agent",
                    "enhengclaw.integrations.openclaw.risk_signal_agent",
                    "enhengclaw.integrations.openclaw.research_synthesizer",
                    "enhengclaw.integrations.openclaw.research_lead",
                ],
            )
            thesis_root = workbench_root / "sol-breakout-20260419"
            cycle_root = thesis_root / "cycles" / "cycle-001"
            self.assertTrue((cycle_root / "market_observer.request.json").exists())
            self.assertTrue((cycle_root / "evidence_agent.request.json").exists())
            self.assertTrue((cycle_root / "risk_signal_agent.response.json").exists())
            self.assertTrue((cycle_root / "cycle_summary.json").exists())
            self.assertTrue((cycle_root / "ohlcv_context.json").exists())
            self.assertTrue((cycle_root / "ohlcv_context.md").exists())
            thesis_profile_path = thesis_root / "thesis_profile.json"
            self.assertTrue(thesis_profile_path.exists())
            market_payload = json.loads((cycle_root / "market_observer.request.json").read_text(encoding="utf-8"))
            self.assertEqual(market_payload["observation_text"], "SOL is still holding above the prior breakout area.")
            self.assertEqual(market_payload["artifacts_root"], str(thesis_root))
            thesis_profile = json.loads(thesis_profile_path.read_text(encoding="utf-8"))
            self.assertEqual(thesis_profile["strategy_profile"], "balanced")
            self.assertEqual(thesis_profile["asset_bucket"], "large_cap")
            self.assertEqual(thesis_profile["history_coverage_status"], "full")
            cycle_summary = json.loads((cycle_root / "cycle_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(cycle_summary["strategy_profile"], "balanced")
            self.assertEqual(cycle_summary["asset_bucket"], "large_cap")
            self.assertEqual(cycle_summary["history_coverage"]["status"], "full")
            self.assertEqual(cycle_summary["market_symbols"]["spot_symbol"], "SOLUSDT")

    def test_existing_object_cycle_skips_market_observer_and_folds_observation_into_synthesis(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_research_cycle_existing_") as tmpdir:
            root = Path(tmpdir)
            workbench_root = root / "workbench"
            thesis_root = workbench_root / "sol-breakout-20260419"
            runtime_session_path = governed_runtime_session_path(
                artifacts_root=thesis_root,
                object_id="sol-breakout-20260419",
            )
            runtime_session_path.parent.mkdir(parents=True, exist_ok=True)
            runtime_session_path.write_text("{}", encoding="utf-8")
            snapshot_path = self._write_snapshot(
                root,
                {
                    "cycle_id": "cycle-002",
                    "cycle_date": "2026-04-20",
                    "object_id": "sol-breakout-20260419",
                    "subject": "SOL",
                    "strategy_profile": "balanced",
                    "asset_bucket": "large_cap",
                    "observation": "SOL is compressing near resistance but has not broken down.",
                    "evidence": "Open interest stayed constructive while perp basis remained controlled.",
                    "risk": "A failed retest would weaken the thesis materially.",
                    "next_step": "Refresh the thesis after the next funding window.",
                },
            )
            provision_summary = {
                "summary_path": str(root / "external" / "provision_summary.json"),
                "permit_path": str(root / "external" / "permit" / "execution_permit.json"),
                "trust_root_dir": str(root / "programdata" / "EnhengClaw" / "trust"),
                "external_root": str(root / "external"),
            }
            recorded_calls: list[tuple[str, dict[str, object], dict[str, str]]] = []

            with patch.object(research_cycle, "provision_openclaw_research_inputs", return_value=provision_summary), patch.object(
                research_cycle,
                "resolve_openclaw_research_operator_env",
                return_value=({"OPENCLAW": "openclaw-secret"}, {"live_env_mode": "unified_openclaw_baseline", "openclaw_mapping_used_by_lane": {}}),
            ), patch.object(research_cycle, "load_symbol_catalog", return_value=self._symbol_catalog()), patch.object(
                research_cycle,
                "build_ohlcv_context",
                side_effect=self._build_ohlcv_context,
            ), patch.object(research_cycle.subprocess, "run", side_effect=self._lane_subprocess_side_effect(recorded_calls)):
                result = research_cycle.run_openclaw_research_cycle(
                    snapshot_path=snapshot_path,
                    workbench_root=workbench_root,
                    compiler_backend="live",
                )

            self.assertEqual(result["status"], "success")
            self.assertFalse(result["created_new_object"])
            cycle_root = thesis_root / "cycles" / "cycle-002"
            self.assertFalse((cycle_root / "market_observer.request.json").exists())
            thesis_profile = json.loads((thesis_root / "thesis_profile.json").read_text(encoding="utf-8"))
            self.assertEqual(thesis_profile["strategy_profile"], "balanced")
            self.assertEqual(thesis_profile["asset_bucket"], "large_cap")
            synthesis_payload = json.loads((cycle_root / "research_synthesizer.request.json").read_text(encoding="utf-8"))
            self.assertIn("SOL is compressing near resistance", synthesis_payload["synthesis_text"])
            self.assertIn("Open interest stayed constructive", synthesis_payload["synthesis_text"])

    def test_existing_object_cycle_reissues_fresh_permit_for_each_resume_lane(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_research_cycle_permits_") as tmpdir:
            root = Path(tmpdir)
            workbench_root = root / "workbench"
            thesis_root = workbench_root / "sol-breakout-20260419"
            runtime_session_path = governed_runtime_session_path(
                artifacts_root=thesis_root,
                object_id="sol-breakout-20260419",
            )
            runtime_session_path.parent.mkdir(parents=True, exist_ok=True)
            runtime_session_path.write_text("{}", encoding="utf-8")
            snapshot_path = self._write_snapshot(
                root,
                {
                    "cycle_id": "cycle-003",
                    "cycle_date": "2026-04-20",
                    "object_id": "sol-breakout-20260419",
                    "subject": "SOL",
                    "strategy_profile": "balanced",
                    "asset_bucket": "large_cap",
                    "observation": "SOL is holding its higher-low structure.",
                    "evidence": "facts=rebid participation improved; interpretation=this keeps the thesis alive; uncertainty=exact baseline still missing",
                    "risk": "A clean rejection back into the range would weaken the setup.",
                    "next_step": "Re-check the thesis after the next funding window.",
                },
            )
            recorded_calls: list[tuple[str, dict[str, object], dict[str, str]]] = []
            provision_counter = {"value": 0}

            def provision_side_effect(**_: object) -> dict[str, object]:
                provision_counter["value"] += 1
                permit_root = root / "external" / f"permit_{provision_counter['value']}"
                return {
                    "summary_path": str(permit_root / "provision_summary.json"),
                    "permit_path": str(permit_root / "execution_permit.json"),
                    "permit_id": f"permit-{provision_counter['value']}",
                    "trust_root_dir": str(root / "programdata" / "EnhengClaw" / "trust"),
                    "external_root": str(root / "external"),
                }

            with patch.object(research_cycle, "provision_openclaw_research_inputs", side_effect=provision_side_effect), patch.object(
                research_cycle,
                "resolve_openclaw_research_operator_env",
                return_value=({"OPENCLAW": "openclaw-secret"}, {"live_env_mode": "unified_openclaw_baseline", "openclaw_mapping_used_by_lane": {}}),
            ), patch.object(research_cycle, "load_symbol_catalog", return_value=self._symbol_catalog()), patch.object(
                research_cycle,
                "build_ohlcv_context",
                side_effect=self._build_ohlcv_context,
            ), patch.object(research_cycle.subprocess, "run", side_effect=self._lane_subprocess_side_effect(recorded_calls)):
                result = research_cycle.run_openclaw_research_cycle(
                    snapshot_path=snapshot_path,
                    workbench_root=workbench_root,
                    compiler_backend="live",
                )

            self.assertEqual(result["status"], "success")
            self.assertEqual(provision_counter["value"], 4)
            permit_paths = [payload["execution_permit_path"] for _, payload, _ in recorded_calls]
            self.assertEqual(
                permit_paths,
                [
                    str(root / "external" / "permit_1" / "execution_permit.json"),
                    str(root / "external" / "permit_2" / "execution_permit.json"),
                    str(root / "external" / "permit_3" / "execution_permit.json"),
                    str(root / "external" / "permit_4" / "execution_permit.json"),
                ],
            )

    @unittest.skipUnless(os.name == "nt", "Long-path cycle response regression is Windows-specific")
    def test_cycle_reads_long_lane_response_paths_on_windows(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="openclaw_research_cycle_long_"))
        try:
            workbench_root = root / "w"
            cycle_id = "cycle"
            cycle_root = workbench_root / "eth-balanced-quant-20260420" / "cycles"
            while len(str(cycle_root / cycle_id / "evidence_agent.response.json")) < 260:
                cycle_id = f"{cycle_id}x"
            snapshot_path = self._write_snapshot(
                root,
                {
                    "cycle_id": cycle_id,
                    "cycle_date": "2026-04-20",
                    "object_id": "eth-balanced-quant-20260420",
                    "subject": "ETH",
                    "scope": "spot+perp",
                    "strategy_profile": "balanced",
                    "asset_bucket": "large_cap",
                    "observation": "ETH holds a constructive large-cap structure.",
                    "evidence": "Quant validation stayed positive out of sample.",
                    "risk": "Invalidate if the next cycle loses OOS stability.",
                    "next_step": "Re-check whether the same signal survives the next daily cycle.",
                },
            )
            provision_summary = {
                "summary_path": str(root / "external" / "provision_summary.json"),
                "permit_path": str(root / "external" / "permit" / "execution_permit.json"),
                "trust_root_dir": str(root / "programdata" / "EnhengClaw" / "trust"),
                "external_root": str(root / "external"),
            }
            recorded_calls: list[tuple[str, dict[str, object], dict[str, str]]] = []

            with patch.object(research_cycle, "provision_openclaw_research_inputs", return_value=provision_summary), patch.object(
                research_cycle,
                "resolve_openclaw_research_operator_env",
                return_value=(
                    {"OPENCLAW": "openclaw-secret"},
                    {"live_env_mode": "unified_openclaw_baseline", "openclaw_mapping_used_by_lane": {}},
                ),
            ), patch.object(research_cycle, "load_symbol_catalog", return_value=self._symbol_catalog()), patch.object(
                research_cycle,
                "build_ohlcv_context",
                side_effect=self._build_ohlcv_context,
            ), patch.object(research_cycle.subprocess, "run", side_effect=self._lane_subprocess_side_effect(recorded_calls)):
                result = research_cycle.run_openclaw_research_cycle(
                    snapshot_path=snapshot_path,
                    workbench_root=workbench_root,
                    compiler_backend="live",
                )

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["lane_results"]["evidence_agent"]["response"]["status"], "success")
            self.assertEqual(result["lane_results"]["risk_signal_agent"]["response"]["status"], "success")
        finally:
            _remove_any_path_tree(root)

    def test_duplicate_cycle_id_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_research_cycle_duplicate_") as tmpdir:
            root = Path(tmpdir)
            workbench_root = root / "workbench"
            existing_cycle_root = workbench_root / "sol-breakout-20260419" / "cycles" / "cycle-001"
            existing_cycle_root.mkdir(parents=True, exist_ok=True)
            snapshot_path = self._write_snapshot(
                root,
                {
                    "cycle_id": "cycle-001",
                    "cycle_date": "2026-04-19",
                    "object_id": "sol-breakout-20260419",
                    "subject": "SOL",
                    "strategy_profile": "balanced",
                    "asset_bucket": "large_cap",
                    "observation": "obs",
                    "evidence": "evidence",
                    "risk": "risk",
                    "next_step": "next",
                },
            )
            with self.assertRaisesRegex(FileExistsError, "research cycle already exists"):
                research_cycle.run_openclaw_research_cycle(
                    snapshot_path=snapshot_path,
                    workbench_root=workbench_root,
                )

    def test_cycle_summary_records_non_blocking_api_reminder_when_threshold_is_crossed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_research_cycle_reminder_") as tmpdir:
            root = Path(tmpdir)
            workbench_root = root / "workbench"
            for thesis_id, cycle_ids in {
                "thesis-a": ("c1", "c2"),
                "thesis-b": ("c3",),
                "thesis-c": ("c4",),
            }.items():
                thesis_root = workbench_root / thesis_id
                thesis_root.mkdir(parents=True, exist_ok=True)
                (thesis_root / "thesis_profile.json").write_text(
                    json.dumps(
                        {
                            "object_id": thesis_id,
                            "subject": thesis_id.upper(),
                            "scope": "spot+perp",
                            "strategy_profile": "conservative",
                            "asset_bucket": "large_cap",
                            "history_coverage_status": "missing",
                            "ohlcv_ready": False,
                            "created_at_utc": "2026-04-18T00:00:00Z",
                            "updated_at_utc": "2026-04-18T00:00:00Z",
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
                pain_log_path = workbench_root / thesis_id / "pain_log.csv"
                pain_log_path.parent.mkdir(parents=True, exist_ok=True)
                rows = [
                    {
                        "object_id": thesis_id,
                        "subject": thesis_id.upper(),
                        "cycle_date": "2026-04-18",
                        "cycle_id": cycle_id,
                        "strategy_profile": "conservative",
                        "asset_bucket": "large_cap",
                        "gap_category": "ohlcv_history",
                        "blocking": "false",
                        "missing_question": "Need more candles",
                        "notes": "Need history",
                        "candidate_api_type": research_cycle.API_LABELS["ohlcv_history"],
                    }
                    for cycle_id in cycle_ids
                ]
                with pain_log_path.open("w", encoding="utf-8", newline="") as handle:
                    handle.write(",".join(research_cycle.PAIN_LOG_HEADERS) + "\n")
                    for row in rows:
                        handle.write(",".join(row[field] for field in research_cycle.PAIN_LOG_HEADERS) + "\n")

            snapshot_path = self._write_snapshot(
                root,
                {
                    "cycle_id": "c5",
                    "cycle_date": "2026-04-19",
                    "object_id": "thesis-d",
                    "subject": "BTC",
                    "strategy_profile": "conservative",
                    "asset_bucket": "large_cap",
                    "observation": "BTC is range-bound after a strong week.",
                    "evidence": "Spot led while perp leverage stayed moderate.",
                    "risk": "Loss of the mid-range could invalidate the idea.",
                    "next_step": "Re-check relative strength tomorrow.",
                    "pain_log": {
                        "gap_category": "ohlcv_history",
                        "blocking": False,
                        "missing_question": "Need a cleaner multi-week candle comparison.",
                        "notes": "The Skills snapshot was not enough to compare the current range to prior squeezes.",
                    },
                },
            )
            provision_summary = {
                "summary_path": str(root / "external" / "provision_summary.json"),
                "permit_path": str(root / "external" / "permit" / "execution_permit.json"),
                "trust_root_dir": str(root / "programdata" / "EnhengClaw" / "trust"),
                "external_root": str(root / "external"),
            }
            recorded_calls: list[tuple[str, dict[str, object], dict[str, str]]] = []

            with patch.object(research_cycle, "provision_openclaw_research_inputs", return_value=provision_summary), patch.object(
                research_cycle,
                "resolve_openclaw_research_operator_env",
                return_value=(
                    {
                        "OPENCLAW": "openclaw-secret",
                        TRUST_ROOT_DIR_ENV: provision_summary["trust_root_dir"],
                    },
                    {"live_env_mode": "unified_openclaw_baseline", "openclaw_mapping_used_by_lane": {}},
                ),
            ), patch.object(research_cycle, "load_symbol_catalog", return_value=self._symbol_catalog()), patch.object(
                research_cycle,
                "build_ohlcv_context",
                side_effect=self._build_ohlcv_context,
            ), patch.object(research_cycle.subprocess, "run", side_effect=self._lane_subprocess_side_effect(recorded_calls)):
                result = research_cycle.run_openclaw_research_cycle(
                    snapshot_path=snapshot_path,
                    workbench_root=workbench_root,
                    compiler_backend="live",
                )

            self.assertEqual(result["status"], "success")
            self.assertTrue(result["api_reminder"]["reminder_triggered"])
            self.assertEqual(result["api_reminder"]["recommended_api_label"], research_cycle.API_LABELS["ohlcv_history"])
            summary_json = json.loads((workbench_root / "api_gap_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary_json["recommendation"]["recommended_gap_category"], "ohlcv_history")
            self.assertTrue((workbench_root / "api_gap_summary.md").exists())
            self.assertTrue((workbench_root / "research_pool_summary.json").exists())
            self.assertTrue((workbench_root / "research_pool_summary.md").exists())

    def test_api_gap_summary_suppresses_ohlcv_recommendation_once_all_theses_are_ready(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_research_cycle_ohlcv_ready_") as tmpdir:
            root = Path(tmpdir)
            workbench_root = root / "workbench"
            for object_id, strategy_profile, asset_bucket in (
                ("eth-conservative-20260420", "conservative", "large_cap"),
                ("sui-balanced-20260420", "balanced", "mid_cap"),
                ("jto-aggressive-20260420", "aggressive", "small_cap"),
            ):
                thesis_root = workbench_root / object_id
                thesis_root.mkdir(parents=True, exist_ok=True)
                (thesis_root / "thesis_profile.json").write_text(
                    json.dumps(
                        {
                            "object_id": object_id,
                            "subject": object_id.split("-")[0].upper(),
                            "scope": "spot+perp",
                            "strategy_profile": strategy_profile,
                            "asset_bucket": asset_bucket,
                            "history_coverage_status": "full",
                            "ohlcv_ready": True,
                            "created_at_utc": "2026-04-20T00:00:00Z",
                            "updated_at_utc": "2026-04-20T00:00:00Z",
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
                (thesis_root / "pain_log.csv").write_text(
                    ",".join(research_cycle.PAIN_LOG_HEADERS)
                    + "\n"
                    + ",".join(
                        [
                            object_id,
                            object_id.split("-")[0].upper(),
                            "2026-04-20",
                            f"{object_id}-cycle-1",
                            strategy_profile,
                            asset_bucket,
                            "ohlcv_history",
                            "false",
                            "Need prior breakout comparison",
                            "Historical placeholder row",
                            research_cycle.API_LABELS["ohlcv_history"],
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )

            summary = research_cycle.evaluate_api_gap_summary(workbench_root=workbench_root)

            self.assertFalse(summary["recommendation"]["reminder_triggered"])
            self.assertIsNone(summary["recommendation"]["recommended_gap_category"])
            self.assertFalse(summary["categories"]["ohlcv_history"]["current_gap_remaining"])

    def test_missing_strategy_profile_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_research_cycle_missing_profile_") as tmpdir:
            root = Path(tmpdir)
            snapshot_path = self._write_snapshot(
                root,
                {
                    "cycle_id": "cycle-010",
                    "cycle_date": "2026-04-20",
                    "object_id": "btc-range-20260420",
                    "subject": "BTC",
                    "asset_bucket": "large_cap",
                    "observation": "BTC remains trapped in range.",
                    "evidence": "Range participation remained balanced.",
                    "risk": "A downside break invalidates the setup.",
                    "next_step": "Review the range after the next session.",
                },
            )
            with self.assertRaisesRegex(ValueError, "strategy_profile is required"):
                research_cycle.run_openclaw_research_cycle(
                    snapshot_path=snapshot_path,
                    workbench_root=root / "workbench",
                )

    def test_existing_profile_metadata_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_research_cycle_profile_mismatch_") as tmpdir:
            root = Path(tmpdir)
            workbench_root = root / "workbench"
            thesis_root = workbench_root / "sol-breakout-20260419"
            runtime_session_path = governed_runtime_session_path(
                artifacts_root=thesis_root,
                object_id="sol-breakout-20260419",
            )
            runtime_session_path.parent.mkdir(parents=True, exist_ok=True)
            runtime_session_path.write_text("{}", encoding="utf-8")
            (thesis_root / "thesis_profile.json").write_text(
                json.dumps(
                    {
                        "object_id": "sol-breakout-20260419",
                        "subject": "SOL",
                        "scope": "spot+perp",
                        "strategy_profile": "balanced",
                        "asset_bucket": "large_cap",
                        "created_at_utc": "2026-04-19T00:00:00Z",
                        "updated_at_utc": "2026-04-19T00:00:00Z",
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            snapshot_path = self._write_snapshot(
                root,
                {
                    "cycle_id": "cycle-011",
                    "cycle_date": "2026-04-20",
                    "object_id": "sol-breakout-20260419",
                    "subject": "SOL",
                    "scope": "spot+perp",
                    "strategy_profile": "aggressive",
                    "asset_bucket": "large_cap",
                    "observation": "SOL is still compressing above support.",
                    "evidence": "Funding stayed controlled.",
                    "risk": "A clean loss of support invalidates the idea.",
                    "next_step": "Re-check after the next major session.",
                },
            )
            provision_summary = {
                "summary_path": str(root / "external" / "provision_summary.json"),
                "permit_path": str(root / "external" / "permit" / "execution_permit.json"),
                "trust_root_dir": str(root / "programdata" / "EnhengClaw" / "trust"),
                "external_root": str(root / "external"),
            }
            with patch.object(research_cycle, "provision_openclaw_research_inputs", return_value=provision_summary), patch.object(
                research_cycle,
                "resolve_openclaw_research_operator_env",
                return_value=({"OPENCLAW": "openclaw-secret"}, {"live_env_mode": "unified_openclaw_baseline", "openclaw_mapping_used_by_lane": {}}),
            ), patch.object(research_cycle, "load_symbol_catalog", return_value=self._symbol_catalog()), patch.object(
                research_cycle,
                "build_ohlcv_context",
                side_effect=self._build_ohlcv_context,
            ):
                result = research_cycle.run_openclaw_research_cycle(
                    snapshot_path=snapshot_path,
                    workbench_root=workbench_root,
                    compiler_backend="live",
                )

            self.assertEqual(result["status"], "failed")
            self.assertIn("metadata mismatch", result["error"])


if __name__ == "__main__":
    unittest.main()
