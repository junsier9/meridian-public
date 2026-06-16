from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
DEFAULT_ALIGNED_RETURNS = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / "2026-05-02-v5-rw-no-overlay-fixed-set-alpha_ontology_h10d_fixed_set_comparison"
    / "aligned_period_returns.csv"
)
DEFAULT_BASELINE = "v5_rw_bridge_no_overlay_h10d"
DEFAULT_COMPARATORS = (
    "lsk3_g_v2_h10d",
    "v5_h10d",
    "v6_h10d",
    "v5_rw_bridge_h10d",
)


@dataclass(frozen=True)
class PeriodRow:
    timestamp_utc: str
    returns: dict[str, float]


def _resolve_repo_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


def _read_rows(path: Path) -> tuple[list[str], list[PeriodRow]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"empty aligned returns file: {path}")
        candidates = [name for name in reader.fieldnames if name not in {"timestamp_ms", "timestamp_utc"}]
        rows: list[PeriodRow] = []
        for row in reader:
            timestamp = str(row.get("timestamp_utc") or "").strip()
            if not timestamp:
                raise ValueError("timestamp_utc is required for confidence slicing")
            rows.append(
                PeriodRow(
                    timestamp_utc=timestamp,
                    returns={candidate: float(row[candidate]) for candidate in candidates},
                )
            )
    if not rows:
        raise ValueError(f"no rows in aligned returns file: {path}")
    return candidates, rows


def _sign_test_pvalue(*, wins: int, losses: int) -> float | None:
    n = int(wins) + int(losses)
    if n <= 0:
        return None
    k = min(int(wins), int(losses))
    tail = sum(math.comb(n, idx) for idx in range(k + 1))
    return float(min(1.0, 2.0 * tail / float(2**n)))


def _basic_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {}
    wins = sum(1 for value in values if value > 0.0)
    losses = sum(1 for value in values if value < 0.0)
    return {
        "n": len(values),
        "sum": float(sum(values)),
        "mean": float(mean(values)),
        "median": float(median(values)),
        "std_population": float(pstdev(values)),
        "win_fraction": float(wins / len(values)),
        "loss_fraction": float(losses / len(values)),
        "min": float(min(values)),
        "max": float(max(values)),
        "sign_test_pvalue_vs_zero": _sign_test_pvalue(wins=wins, losses=losses),
    }


def _slice_stats(rows: list[PeriodRow], values: list[float]) -> dict[str, Any]:
    midpoint = len(values) // 2
    by_year: dict[str, list[float]] = defaultdict(list)
    for row, value in zip(rows, values, strict=True):
        by_year[row.timestamp_utc[:4]].append(value)
    return {
        "first_half": _basic_stats(values[:midpoint]),
        "second_half": _basic_stats(values[midpoint:]),
        "by_year": {year: _basic_stats(year_values) for year, year_values in sorted(by_year.items())},
    }


def _concentration(values: list[float], *, top_n: tuple[int, ...] = (3, 5, 10)) -> dict[str, Any]:
    total = float(sum(values))
    positives = sorted((value for value in values if value > 0.0), reverse=True)
    result: dict[str, Any] = {
        "positive_period_count": len(positives),
        "total_sum": total,
    }
    for n in top_n:
        if total == 0.0:
            share = None
        else:
            share = float(sum(positives[:n]) / total)
        result[f"top_{n}_positive_share_of_total_sum"] = share
    return result


def _drop_extreme_diagnostics(values: list[float], *, n: int = 3) -> dict[str, float | int]:
    ordered = sorted(values)
    best = sorted(values, reverse=True)
    total = float(sum(values))
    return {
        "drop_count": int(n),
        "sum": total,
        "without_best_n_sum": float(total - sum(best[:n])),
        "without_worst_n_sum": float(total - sum(ordered[:n])),
        "best_n_share_of_sum": None if total == 0.0 else float(sum(best[:n]) / total),
    }


def _confidence_verdict(*, standalone: dict[str, Any], pairwise: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {
        "standalone_win_fraction_ge_0_60": float(standalone["overall"]["win_fraction"]) >= 0.60,
        "standalone_both_halves_positive": (
            float(standalone["slices"]["first_half"]["sum"]) > 0.0
            and float(standalone["slices"]["second_half"]["sum"]) > 0.0
        ),
        "standalone_without_top_3_positive": float(
            standalone["drop_extremes"]["without_best_n_sum"]
        )
        > 0.0,
        "paired_all_comparators_positive_sum": all(
            float(item["overall"]["sum"]) > 0.0 for item in pairwise.values()
        ),
        "paired_all_comparators_both_halves_positive": all(
            float(item["slices"]["first_half"]["sum"]) > 0.0
            and float(item["slices"]["second_half"]["sum"]) > 0.0
            for item in pairwise.values()
        ),
        "paired_all_comparators_without_top_3_positive": all(
            float(item["drop_extremes"]["without_best_n_sum"]) > 0.0 for item in pairwise.values()
        ),
    }
    passed = sum(1 for value in checks.values() if value)
    if passed >= 6:
        label = "high"
    elif passed >= 4:
        label = "medium_high"
    elif passed >= 3:
        label = "medium"
    else:
        label = "low"
    warnings: list[str] = []
    top_10_share = standalone["concentration"].get("top_10_positive_share_of_total_sum")
    if top_10_share is not None and float(top_10_share) > 0.65:
        warnings.append("standalone_return_is_materially_concentrated_in_top_10_positive_periods")
    for comparator, item in pairwise.items():
        weak_years = [
            year
            for year, stats in item["slices"]["by_year"].items()
            if int(stats["n"]) >= 6 and float(stats["sum"]) <= 0.0
        ]
        if weak_years:
            warnings.append(f"paired_edge_vs_{comparator}_has_non_positive_years:{','.join(weak_years)}")
    return {
        "label": label,
        "passed_check_count": passed,
        "total_check_count": len(checks),
        "checks": checks,
        "warnings": warnings,
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    baseline = payload["baseline"]
    verdict = payload["verdict"]
    standalone = payload["standalone"]
    lines = [
        "# Baseline Alpha Confidence Validation",
        "",
        f"- Baseline: `{baseline}`",
        f"- Source aligned returns: `{payload['aligned_returns_path']}`",
        f"- OOS window: `{payload['window']['start']}` to `{payload['window']['end']}`",
        f"- Period count: `{payload['window']['period_count']}`",
        f"- Confidence label: `{verdict['label']}` ({verdict['passed_check_count']}/{verdict['total_check_count']} checks passed)",
        "",
        "## Independent Logic",
        "",
        "This diagnostic does not search for new alpha and does not use feature admission logic. It treats the strategy output as a black-box return stream and asks whether the claimed edge survives distributional, temporal, and paired-path stress checks.",
        "",
        "## Standalone Stream",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Sum of period returns | {standalone['overall']['sum']:.6f} |",
        f"| Mean period return | {standalone['overall']['mean']:.6f} |",
        f"| Median period return | {standalone['overall']['median']:.6f} |",
        f"| Win fraction | {standalone['overall']['win_fraction']:.3f} |",
        f"| First-half sum | {standalone['slices']['first_half']['sum']:.6f} |",
        f"| Second-half sum | {standalone['slices']['second_half']['sum']:.6f} |",
        f"| Without best 3 periods sum | {standalone['drop_extremes']['without_best_n_sum']:.6f} |",
        f"| Top 10 positive share of total sum | {standalone['concentration']['top_10_positive_share_of_total_sum']:.3f} |",
        "",
        "## Paired Path Stress",
        "",
        "| Comparator | Sum diff | Win fraction | First-half diff | Second-half diff | Without best 3 diff | Sign p |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for comparator, item in payload["pairwise"].items():
        sign_p = item["overall"]["sign_test_pvalue_vs_zero"]
        sign_p_text = "" if sign_p is None else f"{sign_p:.4f}"
        lines.append(
            f"| `{comparator}` | {item['overall']['sum']:.6f} | {item['overall']['win_fraction']:.3f} | "
            f"{item['slices']['first_half']['sum']:.6f} | {item['slices']['second_half']['sum']:.6f} | "
            f"{item['drop_extremes']['without_best_n_sum']:.6f} | {sign_p_text} |"
        )
    lines.extend(
        [
            "",
            "## Verdict Checks",
            "",
        ]
    )
    for check, passed in verdict["checks"].items():
        marker = "PASS" if passed else "FAIL"
        lines.append(f"- `{marker}` {check}")
    if verdict["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- `{warning}`" for warning in verdict["warnings"])
    return "\n".join(lines) + "\n"


def build_payload(*, aligned_returns_path: Path, baseline: str, comparators: list[str]) -> dict[str, Any]:
    candidates, rows = _read_rows(aligned_returns_path)
    missing = [candidate for candidate in [baseline, *comparators] if candidate not in candidates]
    if missing:
        raise ValueError(f"missing candidates in aligned returns: {missing}")
    baseline_values = [row.returns[baseline] for row in rows]
    standalone = {
        "overall": _basic_stats(baseline_values),
        "slices": _slice_stats(rows, baseline_values),
        "concentration": _concentration(baseline_values),
        "drop_extremes": _drop_extreme_diagnostics(baseline_values),
    }
    pairwise: dict[str, Any] = {}
    for comparator in comparators:
        deltas = [row.returns[baseline] - row.returns[comparator] for row in rows]
        pairwise[comparator] = {
            "overall": _basic_stats(deltas),
            "slices": _slice_stats(rows, deltas),
            "drop_extremes": _drop_extreme_diagnostics(deltas),
        }
    payload = {
        "baseline": baseline,
        "comparators": comparators,
        "aligned_returns_path": str(aligned_returns_path),
        "window": {
            "start": rows[0].timestamp_utc,
            "end": rows[-1].timestamp_utc,
            "period_count": len(rows),
        },
        "standalone": standalone,
        "pairwise": pairwise,
    }
    payload["verdict"] = _confidence_verdict(standalone=standalone, pairwise=pairwise)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate baseline alpha confidence from fixed-set aligned OOS returns."
    )
    parser.add_argument("--aligned-returns", type=Path, default=DEFAULT_ALIGNED_RETURNS)
    parser.add_argument("--baseline", default=DEFAULT_BASELINE)
    parser.add_argument("--comparator", action="append", dest="comparators")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)

    aligned_returns_path = _resolve_repo_path(args.aligned_returns)
    comparators = list(args.comparators or DEFAULT_COMPARATORS)
    payload = build_payload(
        aligned_returns_path=aligned_returns_path,
        baseline=str(args.baseline),
        comparators=comparators,
    )
    output_text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output_dir:
        output_dir = _resolve_repo_path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "baseline_alpha_confidence_validation.json").write_text(
            output_text + "\n",
            encoding="utf-8",
        )
        (output_dir / "baseline_alpha_confidence_validation.md").write_text(
            _render_markdown(payload),
            encoding="utf-8",
        )
    print(output_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
