from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from enhengclaw.adapters.adapters import AdapterBatch
from enhengclaw.core.execution_control import (
    CAP_PROVIDER_FETCH,
    CAP_RUNTIME_EXECUTE,
    ExecutionPermit,
    bind_execution_context,
)
from enhengclaw.core.enums import ObjectType
from enhengclaw.governance.provider_portfolio import ProviderPortfolioInput, ProviderPortfolioReport
from enhengclaw.governance.provider_selection import MODE_DEFAULT, ProviderSelectionError
from enhengclaw.orchestration.provider_snapshot_runner import (
    ProviderSnapshotRunRequest,
    ProviderSnapshotRunResult,
    ProviderSnapshotRunner,
    ProviderSourceSpec,
)
from enhengclaw.orchestration.runtime_runner import RuntimeBoundaryError, RuntimeOrchestrator
from enhengclaw.ops.runtime_ops import RuntimeOpsReport, RuntimeOpsReporter
from enhengclaw.utils.subject_keys import SubjectKey, parse_subject_key_fragment


PILOT_STATUS_OK = "ok"
PILOT_STATUS_RUNTIME_UNAVAILABLE = "runtime_unavailable"
PILOT_STATUS_ERROR = "error"


@dataclass(frozen=True, slots=True)
class PilotArtifactPaths:
    run_root: str
    raw_payload_dir: str
    provider_selection_result: str
    normalized_signal_summary: str
    runtime_result: str | None
    ops_report: str
    warnings_errors: str


@dataclass(frozen=True, slots=True)
class PilotRunResult:
    run_id: str
    status: str
    archive_paths: PilotArtifactPaths
    raw_payload_record_paths: list[str]
    normalized_signal_summary: list[dict[str, object]]
    selection_result: dict[str, object]
    runtime_result: dict[str, object] | None
    ops_report: dict[str, object]
    warnings: list[str]
    errors: list[str]


class PilotRunner:
    def __init__(
        self,
        *,
        runtime: RuntimeOrchestrator | None = None,
        ops_reporter: RuntimeOpsReporter | None = None,
        provider_snapshot_runner: ProviderSnapshotRunner | None = None,
        archive_root: str | Path | None = None,
        execution_permit: ExecutionPermit | None = None,
    ) -> None:
        self.runtime = runtime or RuntimeOrchestrator()
        self.ops_reporter = ops_reporter or RuntimeOpsReporter(getattr(self.runtime, "selection_gateway", None))
        self.provider_snapshot_runner = provider_snapshot_runner or ProviderSnapshotRunner(runtime=self.runtime)
        self.execution_permit = execution_permit
        self.archive_root = (
            Path(archive_root)
            if archive_root is not None
            else Path(__file__).resolve().parents[3] / "artifacts" / "pilot_runs"
        )

    def run_once(
        self,
        *,
        subject: str,
        scope: str,
        provider_inputs: list[ProviderPortfolioInput],
        portfolio_report: ProviderPortfolioReport,
        provider_sources: list[ProviderSourceSpec],
        selection_mode: str = MODE_DEFAULT,
        manual_allowlist: list[str] | None = None,
        object_type: ObjectType = ObjectType.ASSET,
        scenario: str | None = None,
        execution_permit: ExecutionPermit | None = None,
    ) -> PilotRunResult:
        with bind_execution_context(
            execution_permit or self.execution_permit,
            operation="orchestration.pilot_runner.run_once",
            requested_scope=scope,
            required_capabilities={CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH},
        ):
            run_id = self._build_run_id(subject)
            scenario_name = scenario or f"pilot_{subject.lower()}"
            run_subject_key = SubjectKey.build(
                symbol=subject,
                venue="runtime",
                instrument_type="research_object",
            )
            run_root = self.archive_root / run_subject_key.as_path_fragment() / run_id
            raw_payload_dir = run_root / "raw"
            run_root.mkdir(parents=True, exist_ok=True)
            raw_payload_dir.mkdir(parents=True, exist_ok=True)

            ops_report = self.ops_reporter.build(
                provider_inputs=provider_inputs,
                portfolio_report=portfolio_report,
                sources=provider_sources,
            )

            warnings: list[str] = []
            errors: list[str] = []
            if selection_mode != MODE_DEFAULT:
                warnings.append(f"non-default provider selection mode requested: {selection_mode}")

            selection_result_dict: dict[str, object]
            normalized_signal_summary: list[dict[str, object]] = []
            runtime_result_dict: dict[str, object] | None = None
            raw_payload_record_paths: list[str] = []

            try:
                selection = self.runtime.selection_gateway.select(
                    portfolio_report=portfolio_report,
                    sources=provider_sources,
                    mode=selection_mode,
                    manual_allowlist=manual_allowlist,
                )
                if not selection.allowed_sources:
                    raise ProviderSelectionError(
                        "provider selection rejected all candidate providers",
                        selection,
                    )
                selected_sources = list(selection.allowed_sources)
                if not all(isinstance(source, ProviderSourceSpec) for source in selected_sources):
                    raise RuntimeBoundaryError("provider selection returned a non-serializable source candidate")
                snapshot_result = self.provider_snapshot_runner.run_once(
                    ProviderSnapshotRunRequest(
                        object_id=f"pilot:{run_id}:{subject.upper()}",
                        object_type=object_type,
                        subject=subject,
                        scope=scope,
                        scenario=scenario_name,
                        source_specs=selected_sources,
                    ),
                    execution_permit=execution_permit or self.execution_permit,
                )
                selection_result_dict = self._selection_summary(selection)
                normalized_signal_summary = self._normalized_signal_summary(snapshot_result.adapter_batches)
                runtime_result_dict = self._runtime_summary(snapshot_result)
                raw_payload_record_paths = self._materialize_raw_payloads(
                    snapshot_result=snapshot_result,
                    raw_payload_dir=raw_payload_dir,
                )
                status = PILOT_STATUS_OK
            except ProviderSelectionError as exc:
                selection_result_dict = self._selection_summary(exc.selection_result)
                warnings.append("default runtime unavailable; fail closed")
                errors.append(str(exc))
                status = PILOT_STATUS_RUNTIME_UNAVAILABLE
            except RuntimeBoundaryError as exc:
                selection_result_dict = {
                    "mode": selection_mode,
                    "allowed_provider_names": [],
                    "rejected_provider_names": [],
                    "rejected": [],
                }
                warnings.append("canonical provider/snapshot worker lane is unavailable; runtime stays fail-closed")
                errors.append(str(exc))
                status = PILOT_STATUS_RUNTIME_UNAVAILABLE
            except Exception as exc:
                selection_result_dict = {
                    "mode": selection_mode,
                    "allowed_provider_names": [],
                    "rejected_provider_names": [],
                    "rejected": [],
                }
                errors.append(str(exc))
                status = PILOT_STATUS_ERROR

            if not ops_report.runbook.runtime_available and status != PILOT_STATUS_OK:
                warnings.extend(item for item in ops_report.runbook.warnings if item not in warnings)

            artifact_paths = self._write_artifacts(
                run_root=run_root,
                raw_payload_dir=raw_payload_dir,
                selection_result=selection_result_dict,
                normalized_signal_summary=normalized_signal_summary,
                runtime_result=runtime_result_dict,
                ops_report=ops_report,
                warnings=warnings,
                errors=errors,
            )

            return PilotRunResult(
                run_id=run_id,
                status=status,
                archive_paths=artifact_paths,
                raw_payload_record_paths=raw_payload_record_paths,
                normalized_signal_summary=normalized_signal_summary,
                selection_result=selection_result_dict,
                runtime_result=runtime_result_dict,
                ops_report=self._ops_report_summary(ops_report),
                warnings=warnings,
                errors=errors,
            )

    def _materialize_raw_payloads(
        self,
        *,
        snapshot_result: ProviderSnapshotRunResult,
        raw_payload_dir: Path,
    ) -> list[str]:
        paths: list[str] = []
        for provider_name, source_path_value in snapshot_result.source_artifact_paths.items():
            if source_path_value is None:
                continue
            source_path = Path(source_path_value)
            if source_path is None or not source_path.exists():
                continue
            subject_namespace = parse_subject_key_fragment(source_path.parent.name)
            if subject_namespace is None:
                target_path = raw_payload_dir / provider_name / source_path.name
            else:
                target_path = raw_payload_dir / provider_name / subject_namespace.as_path_fragment() / source_path.name
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if source_path.resolve() != target_path.absolute():
                shutil.copy2(source_path, target_path)
            paths.append(str(target_path))
        return paths

    def _selection_summary(self, selection_result) -> dict[str, object]:
        return {
            "mode": selection_result.mode,
            "allowed_provider_names": list(selection_result.allowed_provider_names),
            "rejected_provider_names": list(selection_result.rejected_provider_names),
            "rejected": [asdict(item) for item in selection_result.rejected],
        }

    def _normalized_signal_summary(self, batches: list[AdapterBatch]) -> list[dict[str, object]]:
        summary: list[dict[str, object]] = []
        for batch in batches:
            summary.append(
                {
                    "adapter_name": batch.adapter_name,
                    "provider": batch.source_metadata.get("provider"),
                    "scenario": batch.source_metadata.get("scenario"),
                    "signal_count": len(batch.signals),
                    "signal_ids": [signal.signal_id for signal in batch.signals],
                    "predicates": [signal.predicate for signal in batch.signals],
                    "directions": [signal.direction.value for signal in batch.signals],
                    "evidence_levels": [signal.evidence_level.value for signal in batch.signals],
                }
            )
        return summary

    def _runtime_summary(self, snapshot_result: ProviderSnapshotRunResult) -> dict[str, object]:
        runtime_result = snapshot_result.runtime_result
        return {
            "decision": runtime_result.decision.decision,
            "decision_reasons": list(runtime_result.decision.reasons),
            "research_object": self._to_jsonable(runtime_result.research_object),
            "theses": [self._to_jsonable(thesis) for thesis in runtime_result.theses],
            "cadence": self._to_jsonable(runtime_result.cadence),
            "resource_allocation": self._to_jsonable(runtime_result.resource_allocation),
            "steps": [step.as_dict() for step in runtime_result.steps],
        }

    def _ops_report_summary(self, ops_report: RuntimeOpsReport) -> dict[str, object]:
        return self._to_jsonable(ops_report)

    def _write_artifacts(
        self,
        *,
        run_root: Path,
        raw_payload_dir: Path,
        selection_result: dict[str, object],
        normalized_signal_summary: list[dict[str, object]],
        runtime_result: dict[str, object] | None,
        ops_report: RuntimeOpsReport,
        warnings: list[str],
        errors: list[str],
    ) -> PilotArtifactPaths:
        selection_path = run_root / "provider_selection_result.json"
        normalized_path = run_root / "normalized_signal_summary.json"
        runtime_path = run_root / "runtime_result.json" if runtime_result is not None else None
        ops_path = run_root / "ops_report.json"
        warning_path = run_root / "warnings_errors.json"

        selection_path.write_text(json.dumps(selection_result, indent=2), encoding="utf-8")
        normalized_path.write_text(json.dumps(normalized_signal_summary, indent=2), encoding="utf-8")
        if runtime_path is not None:
            runtime_path.write_text(json.dumps(runtime_result, indent=2), encoding="utf-8")
        ops_path.write_text(json.dumps(self._ops_report_summary(ops_report), indent=2), encoding="utf-8")
        warning_path.write_text(json.dumps({"warnings": warnings, "errors": errors}, indent=2), encoding="utf-8")

        return PilotArtifactPaths(
            run_root=str(run_root),
            raw_payload_dir=str(raw_payload_dir),
            provider_selection_result=str(selection_path),
            normalized_signal_summary=str(normalized_path),
            runtime_result=None if runtime_path is None else str(runtime_path),
            ops_report=str(ops_path),
            warnings_errors=str(warning_path),
        )

    def _build_run_id(self, subject: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_%f")
        slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in subject).strip("_") or "unknown"
        return f"{stamp}_{slug}"

    def _to_jsonable(self, value: Any) -> Any:
        if value is None:
            return None
        if is_dataclass(value):
            return {key: self._to_jsonable(item) for key, item in asdict(value).items()}
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, timedelta):
            return str(value)
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, list):
            return [self._to_jsonable(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._to_jsonable(item) for key, item in value.items()}
        if hasattr(value, "value"):
            return value.value
        return value
