from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from .contracts import utc_now
from .runtime_support import QUANT_INPUT_ROOT
from .lab import run_quant_research_cycle, run_quant_universe_freeze
from .binance_derivatives import resolve_external_derivatives_root
from scripts.market_data.binance_ohlcv import resolve_external_history_root as resolve_binance_ohlcv_root
from scripts.market_data.coinapi_ohlcv import resolve_external_history_root as resolve_coinapi_ohlcv_root


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "benchmarks" / "quant_ohlcv_lanes"


def run_quant_ohlcv_lane_ab(
    *,
    as_of: str,
    compiler_backend: str = "deterministic",
    quant_input_root: Path | None = None,
    ohlcv_external_root: Path | None = None,
    spot_ohlcv_external_root: Path | None = None,
    derivatives_external_root: Path | None = None,
    output_root: Path | None = None,
) -> dict[str, Any]:
    run_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    resolved_quant_input_root = (quant_input_root or QUANT_INPUT_ROOT).expanduser().resolve()
    resolved_binance_ohlcv_root = resolve_binance_ohlcv_root(external_root=ohlcv_external_root)
    resolved_coinapi_spot_root = resolve_coinapi_ohlcv_root(external_root=spot_ohlcv_external_root)
    resolved_derivatives_root = resolve_external_derivatives_root(external_root=derivatives_external_root)
    resolved_output_root = (output_root or (DEFAULT_OUTPUT_ROOT / run_stamp)).expanduser().resolve()
    resolved_output_root.mkdir(parents=True, exist_ok=True)

    lane_configs = (
        ("binance_only", "a_binance", resolved_binance_ohlcv_root, None),
        ("coinapi_spot_binance_fallback", "b_mixed", resolved_binance_ohlcv_root, resolved_coinapi_spot_root),
    )
    lane_results: dict[str, Any] = {}
    for lane_name, lane_dir_name, lane_ohlcv_root, lane_spot_root in lane_configs:
        lane_root = resolved_output_root / lane_dir_name
        lane_artifacts_root = lane_root / "qa"
        lane_workbench_root = lane_root / "wb"
        run_quant_universe_freeze(
            as_of=as_of,
            artifacts_root=lane_artifacts_root,
            quant_input_root=resolved_quant_input_root,
        )
        cycle_summary = run_quant_research_cycle(
            as_of=as_of,
            compiler_backend=compiler_backend,
            artifacts_root=lane_artifacts_root,
            quant_input_root=resolved_quant_input_root,
            workbench_root=lane_workbench_root,
            ohlcv_external_root=lane_ohlcv_root,
            spot_ohlcv_external_root=lane_spot_root,
            derivatives_external_root=resolved_derivatives_root,
            auto_detect_spot_ohlcv_external_root=lane_spot_root is not None,
        )
        lane_results[lane_name] = {
            "artifacts_root": str(lane_artifacts_root),
            "workbench_root": str(lane_workbench_root),
            "quant_cycle_summary_path": str(cycle_summary["quant_cycle_summary_path"]),
            "spot_provider_lane": cycle_summary["spot_provider_lane"],
            "dataset_subject_counts": dict(cycle_summary.get("dataset_subject_counts") or {}),
            "dataset_row_counts": dict(cycle_summary.get("dataset_row_counts") or {}),
            "feature_row_counts": dict(cycle_summary.get("feature_row_counts") or {}),
            "trainable_strategy_count": int(cycle_summary.get("trainable_strategy_count", 0) or 0),
            "train_split_row_count_total": int(cycle_summary.get("train_split_row_count_total", 0) or 0),
        }

    baseline = lane_results["binance_only"]
    mixed = lane_results["coinapi_spot_binance_fallback"]
    comparison = {
        "dataset_subject_count_delta": _diff_map(
            left=mixed["dataset_subject_counts"],
            right=baseline["dataset_subject_counts"],
        ),
        "dataset_row_count_delta": _diff_map(
            left=mixed["dataset_row_counts"],
            right=baseline["dataset_row_counts"],
        ),
        "feature_row_count_delta": _diff_map(
            left=mixed["feature_row_counts"],
            right=baseline["feature_row_counts"],
        ),
        "trainable_strategy_count_delta": (
            int(mixed["trainable_strategy_count"]) - int(baseline["trainable_strategy_count"])
        ),
        "train_split_row_count_total_delta": (
            int(mixed["train_split_row_count_total"]) - int(baseline["train_split_row_count_total"])
        ),
    }
    summary = {
        "generated_at_utc": utc_now(),
        "status": "success",
        "success": True,
        "as_of": as_of,
        "compiler_backend": compiler_backend,
        "output_root": str(resolved_output_root),
        "quant_input_root": str(resolved_quant_input_root),
        "ohlcv_external_root": str(resolved_binance_ohlcv_root),
        "spot_ohlcv_external_root": str(resolved_coinapi_spot_root),
        "derivatives_external_root": str(resolved_derivatives_root),
        "lane_results": lane_results,
        "comparison": comparison,
    }
    summary_path = resolved_output_root / "lane_ab_summary.json"
    markdown_path = resolved_output_root / "lane_ab_summary.md"
    summary["summary_path"] = str(summary_path)
    summary["markdown_path"] = str(markdown_path)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_build_markdown(summary) + "\n", encoding="utf-8")
    return summary


def _diff_map(*, left: dict[str, Any], right: dict[str, Any]) -> dict[str, int]:
    keys = sorted(set(left) | set(right))
    return {
        key: int(left.get(key, 0) or 0) - int(right.get(key, 0) or 0)
        for key in keys
    }


def _build_markdown(summary: dict[str, Any]) -> str:
    baseline = summary["lane_results"]["binance_only"]
    mixed = summary["lane_results"]["coinapi_spot_binance_fallback"]
    lines = [
        "# Quant OHLCV Lane A/B",
        "",
        f"- Generated at: `{summary['generated_at_utc']}`",
        f"- As of: `{summary['as_of']}`",
        f"- Binance OHLCV root: `{summary['ohlcv_external_root']}`",
        f"- CoinAPI spot root: `{summary['spot_ohlcv_external_root']}`",
        "",
        "## Lane Summary",
        "",
        f"- Binance-only trainable strategies: `{baseline['trainable_strategy_count']}`",
        f"- Mixed-lane trainable strategies: `{mixed['trainable_strategy_count']}`",
        f"- Binance-only train split rows: `{baseline['train_split_row_count_total']}`",
        f"- Mixed-lane train split rows: `{mixed['train_split_row_count_total']}`",
        "",
        "## Dataset Deltas (Mixed - Binance)",
        "",
    ]
    for dataset_id, delta in summary["comparison"]["dataset_subject_count_delta"].items():
        row_delta = summary["comparison"]["dataset_row_count_delta"].get(dataset_id, 0)
        lines.append(
            f"- `{dataset_id}` subject_delta=`{delta}` row_delta=`{row_delta}`"
        )
    lines.extend(
        [
            "",
            "## Feature Deltas (Mixed - Binance)",
            "",
        ]
    )
    for feature_set_id, delta in summary["comparison"]["feature_row_count_delta"].items():
        lines.append(f"- `{feature_set_id}` row_delta=`{delta}`")
    return "\n".join(lines)
