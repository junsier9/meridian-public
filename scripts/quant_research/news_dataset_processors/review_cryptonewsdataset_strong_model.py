"""Run a stronger-model review pass on high-priority crypto news labels.

Inputs:
    artifacts/quant_research/datasets/<as_of>-crypto-news-dataset/
        - llm_structured_scores.parquet
        - strong_model_review_candidates.parquet

Outputs:
    artifacts/quant_research/datasets/<as_of>-crypto-news-dataset/
        - strong_model_review_priority_ge_<n>.jsonl
        - strong_model_review_priority_ge_<n>.parquet
        - llm_structured_scores_adjudicated_priority_ge_<n>.parquet
        - strong_model_review_priority_ge_<n>_report.json
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Literal

from openai import OpenAI
import pandas as pd
from pydantic import BaseModel, Field
from tqdm import tqdm

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.contracts import portable_path, write_json
from scripts.quant_research.news_dataset_processors.process_cryptonewsdataset_llm import (
    SYSTEM_PROMPT,
    _safe_int,
    _safe_text,
)


CARD_CONTRACT_VERSION = "quant_crypto_news_dataset_strong_review.v1"
DEFAULT_MODEL = "gpt-5"
DEFAULT_REASONING_EFFORT = "low"
DEFAULT_PRIORITY_THRESHOLD = 8
DEFAULT_MAX_WORKERS = 4
DEFAULT_MAX_OUTPUT_TOKENS = 1200
NARRATIVE_TAXONOMY = (
    "bitcoin",
    "ethereum",
    "solana",
    "layer2",
    "defi",
    "stablecoins",
    "etf",
    "regulation",
    "macro",
    "security",
    "memecoins",
    "ai",
    "rwa",
    "depin",
    "gaming",
    "nft",
    "onchain",
    "exchanges",
    "derivatives",
    "mining",
)
LABEL_FIELDS = [
    "news_kind",
    "event_type",
    "market_impact_direction",
    "market_impact_magnitude",
    "repricing_type",
    "subject_link_strength",
    "tradability_risk",
    "decay_horizon_days",
    "is_actionable_event",
    "short_veto_flag",
    "narrative_tags",
    "summary",
    "rationale",
]


class StrongReviewAssessment(BaseModel):
    news_kind: Literal["hard_event", "reporting", "analysis", "opinion", "social_post", "roundup"]
    event_type: Literal[
        "exchange_listing",
        "exchange_delisting",
        "security_incident",
        "regulatory",
        "partnership",
        "product_launch",
        "protocol_upgrade",
        "governance",
        "token_unlock",
        "funding_round",
        "etf",
        "macro",
        "stablecoin",
        "mining",
        "market_structure",
        "legal",
        "research_report",
        "other",
    ]
    market_impact_direction: Literal["bullish", "bearish", "neutral", "mixed"]
    market_impact_magnitude: int = Field(ge=0, le=5)
    repricing_type: Literal["real_repricing", "hype", "mixed", "unclear"]
    subject_link_strength: int = Field(ge=0, le=5)
    tradability_risk: Literal["low", "medium", "high"]
    decay_horizon_days: Literal[1, 3, 5, 10, 20, 30]
    is_actionable_event: bool
    short_veto_flag: bool
    narrative_tags: list[
        Literal[
            "bitcoin",
            "ethereum",
            "solana",
            "layer2",
            "defi",
            "stablecoins",
            "etf",
            "regulation",
            "macro",
            "security",
            "memecoins",
            "ai",
            "rwa",
            "depin",
            "gaming",
            "nft",
            "onchain",
            "exchanges",
            "derivatives",
            "mining",
        ]
    ]
    summary: str
    rationale: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=datetime.now(UTC).date().isoformat())
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--reasoning-effort", default=DEFAULT_REASONING_EFFORT)
    parser.add_argument("--priority-threshold", type=int, default=DEFAULT_PRIORITY_THRESHOLD)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    return parser.parse_args()


def _load_existing_review_ids(output_jsonl: Path) -> set[int]:
    if not output_jsonl.exists():
        return set()
    seen: set[int] = set()
    for raw_line in output_jsonl.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        seen.add(int(payload["id"]))
    return seen


def _append_jsonl(path: Path, payloads: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for payload in payloads:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _safe_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, dict)):
        converted = value.tolist()
        if converted is None:
            return []
        if isinstance(converted, list):
            return converted
        if isinstance(converted, tuple):
            return list(converted)
        return [converted]
    try:
        if pd.isna(value):
            return []
    except Exception:
        pass
    return [value]


def _review_input_payload(row: pd.Series) -> str:
    payload = {
        "title": _safe_text(row.get("title")),
        "description": _safe_text(row.get("description"))[:1600],
        "source_domain": _safe_text(row.get("sourceDomain")),
        "source_kind": _safe_text(row.get("source_kind")),
        "source_url": _safe_text(row.get("sourceUrl")),
        "news_datetime_utc": _safe_text(row.get("newsDatetime_utc")),
        "currencies": ", ".join(str(item) for item in _safe_list(row.get("currencies"))),
        "reaction_sum": _safe_int(row.get("reaction_sum")),
        "engagement_sum": _safe_int(row.get("engagement_sum")),
        "important_votes": _safe_int(row.get("important")),
        "positive_votes": _safe_int(row.get("positive")),
        "negative_votes": _safe_int(row.get("negative")),
    }
    return json.dumps(payload, ensure_ascii=False)


def _score_row_strong(
    row: pd.Series,
    *,
    model: str,
    reasoning_effort: str,
    max_output_tokens: int,
    max_retries: int = 3,
) -> StrongReviewAssessment:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.responses.parse(
                model=model,
                reasoning={"effort": reasoning_effort},
                max_output_tokens=max_output_tokens,
                instructions=SYSTEM_PROMPT,
                input=_review_input_payload(row),
                text_format=StrongReviewAssessment,
            )
            return response.output_parsed
        except Exception as exc:  # pragma: no cover - exercised in live run
            last_error = exc
            if attempt >= max_retries:
                break
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"Strong review failed after {max_retries} attempts: {last_error}") from last_error


def _normalize_compare_value(value: Any) -> Any:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, dict)):
        converted = value.tolist()
        if isinstance(converted, list):
            return converted
        if isinstance(converted, tuple):
            return list(converted)
        return converted
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _changed_fields(row: pd.Series, strong_payload: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    for field in LABEL_FIELDS:
        mini_value = _normalize_compare_value(row.get(field))
        strong_value = _normalize_compare_value(strong_payload.get(field))
        if mini_value != strong_value:
            changed.append(field)
    return changed


def _review_output_row(
    row: pd.Series,
    strong_assessment: StrongReviewAssessment,
    *,
    model: str,
    reasoning_effort: str,
) -> dict[str, Any]:
    strong_payload = strong_assessment.model_dump()
    changed_fields = _changed_fields(row, strong_payload)
    payload: dict[str, Any] = {
        "id": int(row["id"]),
        "title": str(row["title"]),
        "strong_review_generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "strong_review_model": model,
        "strong_review_reasoning_effort": reasoning_effort,
        "strong_model_review_rank": int(row["strong_model_review_rank"]),
        "strong_model_review_priority": int(row["strong_model_review_priority"]),
        "strong_model_review_reasons": list(row["strong_model_review_reasons"]),
        "mini_vs_strong_changed_fields": changed_fields,
        "mini_vs_strong_change_count": len(changed_fields),
        "mini_vs_strong_any_change": bool(changed_fields),
    }
    for field, value in strong_payload.items():
        payload[f"strong_{field}"] = value
    return payload


def _build_adjudicated_frame(mini_frame: pd.DataFrame, review_frame: pd.DataFrame) -> pd.DataFrame:
    adjudicated = mini_frame.copy()
    review_columns = ["id"] + [column for column in review_frame.columns if column != "id"]
    adjudicated = adjudicated.merge(review_frame[review_columns], on="id", how="left")
    adjudicated["was_strong_reviewed"] = adjudicated["strong_review_model"].notna()
    adjudicated["final_label_source"] = adjudicated["was_strong_reviewed"].map(lambda value: "strong_review" if value else "mini")
    adjudicated["mini_vs_strong_change_count"] = adjudicated["mini_vs_strong_change_count"].fillna(0).astype(int)
    adjudicated["mini_vs_strong_any_change"] = adjudicated["mini_vs_strong_any_change"].map(
        lambda value: bool(value) if pd.notna(value) else False
    )
    for field in LABEL_FIELDS:
        strong_column = f"strong_{field}"
        final_column = f"final_{field}"
        adjudicated[final_column] = adjudicated[strong_column].where(adjudicated["was_strong_reviewed"], adjudicated[field])
    return adjudicated


def main() -> None:
    args = _parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required")

    output_root = ROOT / "artifacts" / "quant_research" / "datasets" / f"{args.as_of}-crypto-news-dataset"
    candidates_parquet = output_root / "strong_model_review_candidates.parquet"
    mini_parquet = output_root / "llm_structured_scores.parquet"
    if not candidates_parquet.exists():
        raise FileNotFoundError(f"missing candidates parquet: {candidates_parquet}")
    if not mini_parquet.exists():
        raise FileNotFoundError(f"missing mini parquet: {mini_parquet}")

    suffix = f"priority_ge_{int(args.priority_threshold)}"
    review_jsonl = output_root / f"strong_model_review_{suffix}.jsonl"
    review_parquet = output_root / f"strong_model_review_{suffix}.parquet"
    adjudicated_parquet = output_root / f"llm_structured_scores_adjudicated_{suffix}.parquet"
    report_json = output_root / f"strong_model_review_{suffix}_report.json"

    mini_frame = pd.read_parquet(mini_parquet)
    candidates_frame = pd.read_parquet(candidates_parquet)
    target_frame = candidates_frame.loc[candidates_frame["strong_model_review_priority"].ge(int(args.priority_threshold))].copy()
    target_frame = target_frame.sort_values(["strong_model_review_rank", "id"]).reset_index(drop=True)

    existing_ids = _load_existing_review_ids(review_jsonl)
    pending_rows = [row for _, row in target_frame.iterrows() if int(row["id"]) not in existing_ids]

    completed_payloads: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []
    if pending_rows:
        with ThreadPoolExecutor(max_workers=max(1, int(args.max_workers))) as executor:
            futures = {
                executor.submit(
                    _score_row_strong,
                    row,
                    model=args.model,
                    reasoning_effort=args.reasoning_effort,
                    max_output_tokens=int(args.max_output_tokens),
                ): row
                for row in pending_rows
            }
            for future in tqdm(as_completed(futures), total=len(futures), desc="Strong review", unit="article"):
                row = futures[future]
                try:
                    strong_assessment = future.result()
                    completed_payloads.append(
                        _review_output_row(
                            row,
                            strong_assessment,
                            model=args.model,
                            reasoning_effort=args.reasoning_effort,
                        )
                    )
                    if len(completed_payloads) >= 10:
                        _append_jsonl(review_jsonl, completed_payloads)
                        completed_payloads = []
                except Exception as exc:  # pragma: no cover - exercised in live run
                    error_rows.append({"id": int(row["id"]), "title": str(row["title"]), "error": str(exc)})
        if completed_payloads:
            _append_jsonl(review_jsonl, completed_payloads)

    reviewed_rows: list[dict[str, Any]] = []
    if review_jsonl.exists():
        for raw_line in review_jsonl.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if line:
                reviewed_rows.append(json.loads(line))
    review_frame = pd.DataFrame(reviewed_rows)
    if not review_frame.empty:
        review_frame = review_frame.sort_values(["strong_model_review_rank", "id"]).reset_index(drop=True)
        review_frame.to_parquet(review_parquet, index=False)

    adjudicated_frame = _build_adjudicated_frame(mini_frame, review_frame)
    adjudicated_frame.to_parquet(adjudicated_parquet, index=False)

    field_change_counts: dict[str, int] = {}
    if not review_frame.empty:
        exploded = review_frame["mini_vs_strong_changed_fields"].explode().dropna()
        field_change_counts = {str(key): int(value) for key, value in exploded.value_counts().to_dict().items()}

    summary = {
        "contract_version": CARD_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "review_parameters": {
            "model": args.model,
            "reasoning_effort": args.reasoning_effort,
            "priority_threshold": int(args.priority_threshold),
            "max_workers": int(args.max_workers),
            "max_output_tokens": int(args.max_output_tokens),
        },
        "review_scope": {
            "target_rows": int(len(target_frame)),
            "reviewed_rows": int(len(review_frame)),
            "pending_rows": int(max(len(target_frame) - len(review_frame), 0)),
            "error_rows": error_rows,
        },
        "agreement_summary": {
            "any_change_rate": float(review_frame["mini_vs_strong_any_change"].mean()) if not review_frame.empty else 0.0,
            "mean_change_count": float(review_frame["mini_vs_strong_change_count"].mean()) if not review_frame.empty else 0.0,
            "field_change_counts": field_change_counts,
        },
        "artifacts": {
            "review_jsonl": portable_path(review_jsonl),
            "review_parquet": portable_path(review_parquet) if review_parquet.exists() else None,
            "adjudicated_parquet": portable_path(adjudicated_parquet),
        },
    }
    write_json(report_json, summary)

    print(f"target_rows={len(target_frame)}")
    print(f"reviewed_rows={len(review_frame)}")
    print(f"adjudicated_rows={len(adjudicated_frame)}")
    print(f"output_root={output_root}")


if __name__ == "__main__":
    main()
