from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.entry_second_canary_selector import (  # noqa: E402
    build_entry_second_canary_selector_result,
    default_selector_contract,
)
from enhengclaw.quant_research.contracts import write_json  # noqa: E402


DEFAULT_OUTPUT_ROOT = "artifacts/governance/entry_second_canary_selector_dry_run"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run only entry_second canary selector gate. It reads retained plan artifacts, "
            "selects a bounded canary subset, and optionally validates an owner payload hash "
            "binding. It never opens a budget epoch, arms live_delta, invokes systemd, or submits orders."
        )
    )
    parser.add_argument(
        "--plan-root",
        action="append",
        default=[],
        help="Plan artifact root containing summary.json and order_sizing_report.csv. Repeat for stability samples.",
    )
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-label", default="")
    parser.add_argument("--owner-payload-json", default="", help="Optional JSON object or @path for hash-binding validation.")
    parser.add_argument("--max-order-count", type=int, default=4)
    parser.add_argument("--max-turnover-usdt", type=float, default=75.0)
    parser.add_argument("--required-stability-samples", type=int, default=2)
    parser.add_argument("--notional-buffer-multiplier", type=float, default=1.5)
    parser.add_argument("--notional-buffer-additive-usdt", type=float, default=2.5)
    args = parser.parse_args(argv)

    summary = run_entry_second_canary_selector_dry_run(
        plan_roots=[Path(item) for item in list(args.plan_root or [])],
        output_root=Path(args.output_root),
        run_label=str(args.run_label or ""),
        owner_payload_json=str(args.owner_payload_json or ""),
        max_order_count=int(args.max_order_count),
        max_turnover_usdt=float(args.max_turnover_usdt),
        required_stability_samples=int(args.required_stability_samples),
        notional_buffer_multiplier=float(args.notional_buffer_multiplier),
        notional_buffer_additive_usdt=float(args.notional_buffer_additive_usdt),
    )
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0 if summary["status"] == "passed" else 2


def run_entry_second_canary_selector_dry_run(
    *,
    plan_roots: list[Path],
    output_root: Path,
    run_label: str = "",
    owner_payload_json: str = "",
    max_order_count: int = 4,
    max_turnover_usdt: float = 75.0,
    required_stability_samples: int = 2,
    notional_buffer_multiplier: float = 1.5,
    notional_buffer_additive_usdt: float = 2.5,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = run_label.strip() or generated_at.strftime("%Y%m%dT%H%M%SZ")
    run_root = output_root / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    contract = default_selector_contract(
        max_order_count=max_order_count,
        max_turnover_usdt=max_turnover_usdt,
        required_stability_samples=required_stability_samples,
        notional_buffer_multiplier=notional_buffer_multiplier,
        notional_buffer_additive_usdt=notional_buffer_additive_usdt,
    )
    owner_payload = _owner_payload_from_arg(owner_payload_json)
    selector_result = build_entry_second_canary_selector_result(
        plan_roots=plan_roots,
        contract=contract,
        owner_payload=owner_payload,
    )

    contract_path = run_root / "canary_selector_contract.json"
    result_path = run_root / "selector_result.json"
    owner_template_path = run_root / "owner_payload_template.json"
    summary_path = run_root / "summary.json"
    write_json(contract_path, contract)
    write_json(result_path, selector_result)
    write_json(owner_template_path, selector_result["owner_payload_template"])

    owner_binding = dict(selector_result.get("owner_payload_binding") or {})
    status = "passed" if selector_result["status"] == "passed" and str(owner_binding.get("status")) in {"not_provided", "passed"} else "blocked"
    summary = {
        "contract_version": "entry_second_canary_selector_dry_run_gate.v1",
        "run_id": run_id,
        "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": list(selector_result.get("blockers") or [])
        + [f"owner_payload_binding:{item}" for item in list(owner_binding.get("blockers") or [])],
        "plan_roots": [str(path) for path in plan_roots],
        "selected_symbols": list(selector_result.get("selected_symbols") or []),
        "selected_order_count": int(selector_result.get("selected_order_count") or 0),
        "selected_turnover_usdt": float(selector_result.get("selected_turnover_usdt") or 0.0),
        "selector_contract_sha256": selector_result.get("contract_sha256"),
        "selector_output_sha256": selector_result.get("selector_output_sha256"),
        "owner_payload_binding_status": owner_binding.get("status"),
        "non_authorizations": selector_result["non_authorizations"],
        "output_files": {
            "contract": str(contract_path),
            "selector_result": str(result_path),
            "owner_payload_template": str(owner_template_path),
            "summary": str(summary_path),
        },
    }
    write_json(summary_path, summary)
    return summary


def _owner_payload_from_arg(raw_value: str) -> dict[str, Any] | None:
    raw = str(raw_value or "").strip()
    if not raw:
        return None
    if raw.startswith("@"):
        loaded = json.loads(Path(raw[1:]).read_text(encoding="utf-8"))
    elif raw.startswith("{"):
        loaded = json.loads(raw)
    else:
        candidate = Path(raw)
        if candidate.exists():
            loaded = json.loads(candidate.read_text(encoding="utf-8"))
        else:
            loaded = json.loads(raw)
    if not isinstance(loaded, dict):
        raise ValueError("owner_payload_json_must_be_object")
    return dict(loaded)


if __name__ == "__main__":
    raise SystemExit(main())
