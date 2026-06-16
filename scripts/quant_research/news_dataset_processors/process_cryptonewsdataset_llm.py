"""Ingest and LLM-structure soheilrahsaz/cryptoNewsDataset for quant research.

This script is deliberately conservative on time semantics:

- `newsDatetime` is treated as source-published time only
- `research_effective_at_utc` is set to next UTC day open for PIT-safe research
- `reaction_sum` / `engagement_sum` are used as quality filters, never as
  first-seen proxies

Outputs:
    artifacts/quant_research/datasets/<as_of>-crypto-news-dataset/
        - high_quality_crypto_news.parquet
        - high_quality_crypto_news.csv.gz
        - llm_scoring_input.csv.gz
        - llm_structured_scores.jsonl
        - llm_structured_scores.parquet
        - strong_model_review_candidates.csv.gz
        - strong_model_review_candidates.parquet
        - processing_report.json
        - scoring_state.json
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from openai import OpenAI
import pandas as pd
from tqdm import tqdm

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.contracts import portable_path, write_json


CARD_CONTRACT_VERSION = "quant_crypto_news_dataset_llm.v1"
DEFAULT_DATASET_REPO_URL = "https://github.com/soheilrahsaz/cryptoNewsDataset.git"
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_MIN_YEAR = 2021
DEFAULT_MIN_REACTION_SUM = 4
DEFAULT_MAX_ROWS = 180
DEFAULT_MAX_WORKERS = 4

SOCIAL_DOMAIN_EXACT = {
    "twitter.com",
    "x.com",
    "reddit.com",
    "r/ecash",
    "youtube.com",
    "youtu.be",
    "telegram.org",
    "t.me",
}
OFFICIAL_DOMAIN_HINTS = (
    "binance.com",
    "coinbase.com",
    "kraken.com",
    "bybit.com",
    "okx.com",
    "ethereum.org",
    "solana.com",
    "optimism.io",
    "arbitrum.io",
    "aptosfoundation.org",
    "avax.network",
)
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
LLM_SCHEMA = {
    "name": "crypto_news_research_assessment",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "news_kind": {
                "type": "string",
                "enum": [
                    "hard_event",
                    "reporting",
                    "analysis",
                    "opinion",
                    "social_post",
                    "roundup",
                ],
            },
            "event_type": {
                "type": "string",
                "enum": [
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
                ],
            },
            "market_impact_direction": {
                "type": "string",
                "enum": ["bullish", "bearish", "neutral", "mixed"],
            },
            "market_impact_magnitude": {"type": "integer", "minimum": 0, "maximum": 5},
            "repricing_type": {
                "type": "string",
                "enum": ["real_repricing", "hype", "mixed", "unclear"],
            },
            "subject_link_strength": {"type": "integer", "minimum": 0, "maximum": 5},
            "tradability_risk": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
            "decay_horizon_days": {
                "type": "integer",
                "enum": [1, 3, 5, 10, 20, 30],
            },
            "is_actionable_event": {"type": "boolean"},
            "short_veto_flag": {"type": "boolean"},
            "narrative_tags": {
                "type": "array",
                "items": {"type": "string", "enum": list(NARRATIVE_TAXONOMY)},
                "maxItems": 5,
            },
            "summary": {"type": "string", "maxLength": 220},
            "rationale": {"type": "string", "maxLength": 320},
        },
        "required": [
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
        ],
        "additionalProperties": False,
    },
}
SYSTEM_PROMPT = """You are a world-class crypto event-driven quant researcher.

Classify each article for use in event-tape and post-pump short-veto research.

Important rules:
- Be conservative about calling something a real repricing event.
- `short_veto_flag=true` only if the article likely represents a genuine,
  durable repricing catalyst or official event where shorting immediately after
  a pump would be dangerous.
- `hype` means attention-driven, promotional, reflexive, or weakly substantiated.
- If the article is mainly commentary, opinion, or a low-information roundup,
  set `is_actionable_event=false`.
- Use only the information in the article fields provided.
- Return strict JSON matching the schema.
"""


def _default_repo_root() -> Path:
    return Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".").resolve() / "cryptoNewsDataset_eval"


def _run(args: list[str]) -> None:
    subprocess.run(args, check=True)


def _ensure_repo(repo_root: Path, *, repo_url: str) -> None:
    if repo_root.exists():
        return
    repo_root.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", "--depth", "1", repo_url, str(repo_root)])


def _extract_rar_member(archive_path: Path, destination_dir: Path) -> None:
    destination_dir.mkdir(parents=True, exist_ok=True)
    _run(["tar", "-xf", str(archive_path), "-C", str(destination_dir)])


def _normalize_nullable_text(series: pd.Series) -> pd.Series:
    normalized = series.astype("string").replace({"NULL": pd.NA, "null": pd.NA, "None": pd.NA})
    return normalized.where(normalized.str.strip().ne(""), pd.NA)


def _safe_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _safe_int(value: Any) -> int:
    if value is None or pd.isna(value):
        return 0
    return int(value)


def _domain_kind(domain: str | None) -> str:
    normalized = _safe_text(domain).lower()
    if not normalized:
        return "unknown"
    if normalized in SOCIAL_DOMAIN_EXACT:
        return "social"
    if any(hint in normalized for hint in OFFICIAL_DOMAIN_HINTS):
        return "official"
    return "editorial"


def _research_effective_at(news_dt: pd.Timestamp) -> str | None:
    if pd.isna(news_dt):
        return None
    dt = news_dt.to_pydatetime().replace(tzinfo=UTC)
    next_day = datetime(dt.year, dt.month, dt.day, tzinfo=UTC) + timedelta(days=1)
    return next_day.isoformat().replace("+00:00", "Z")


def _compute_quality_score(frame: pd.DataFrame) -> pd.Series:
    reaction_component = frame["reaction_sum"].clip(lower=0).map(lambda x: min(math.log1p(float(x)) / math.log1p(50.0), 1.0))
    description_component = frame["description"].notna().astype(float)
    sourceurl_component = frame["sourceUrl"].notna().astype(float)
    editorial_component = frame["source_kind"].isin(("editorial", "official")).astype(float)
    return (
        0.45 * reaction_component
        + 0.20 * description_component
        + 0.15 * sourceurl_component
        + 0.20 * editorial_component
    )


def _split_currencies(value: Any) -> list[str]:
    if value is None or pd.isna(value):
        return []
    items: list[str] = []
    for raw in str(value).split(","):
        item = raw.strip().upper()
        if item and item not in items:
            items.append(item)
    return items


def _prepare_dataset(joined_csv_path: Path, *, min_year: int, min_reaction_sum: int, exclude_social: bool) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = pd.read_csv(joined_csv_path, low_memory=False)
    for column in ("title", "description", "sourceDomain", "sourceUrl", "url", "currencies"):
        frame[column] = _normalize_nullable_text(frame[column])

    numeric_columns = ("negative", "positive", "important", "liked", "disliked", "lol", "toxic", "saved", "comments")
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0).astype(int)
    frame["newsDatetime"] = pd.to_datetime(frame["newsDatetime"], errors="coerce", utc=True)

    frame["reaction_sum"] = (
        frame["negative"]
        + frame["positive"]
        + frame["important"]
        + frame["liked"]
        + frame["disliked"]
        + frame["lol"]
        + frame["toxic"]
        + frame["saved"]
    )
    frame["engagement_sum"] = frame["reaction_sum"] + frame["comments"]
    frame["source_kind"] = frame["sourceDomain"].map(_domain_kind)
    frame["currencies_list"] = frame["currencies"].map(_split_currencies)
    frame["currency_count"] = frame["currencies_list"].map(len)
    frame["research_effective_at_utc"] = frame["newsDatetime"].map(_research_effective_at)
    frame["quality_score"] = _compute_quality_score(frame)

    pre_filter = {
        "rows": int(len(frame)),
        "min_news_datetime_utc": frame["newsDatetime"].min().isoformat().replace("+00:00", "Z") if frame["newsDatetime"].notna().any() else None,
        "max_news_datetime_utc": frame["newsDatetime"].max().isoformat().replace("+00:00", "Z") if frame["newsDatetime"].notna().any() else None,
        "source_kind_counts": frame["source_kind"].value_counts(dropna=False).to_dict(),
    }

    mask = frame["newsDatetime"].dt.year.ge(min_year)
    mask &= frame["reaction_sum"].ge(min_reaction_sum)
    mask &= frame["title"].notna()
    mask &= frame["source_kind"].isin(("editorial", "official")) if exclude_social else True
    mask &= frame["sourceUrl"].notna() | frame["description"].notna()
    filtered = frame.loc[mask].copy()
    filtered = filtered.sort_values(["newsDatetime", "reaction_sum", "quality_score"], ascending=[False, False, False]).reset_index(drop=True)
    filtered["selection_rank"] = range(1, len(filtered) + 1)

    summary = {
        "pre_filter": pre_filter,
        "post_filter": {
            "rows": int(len(filtered)),
            "unique_source_domains": int(filtered["sourceDomain"].nunique(dropna=True)),
            "top_source_domains": filtered["sourceDomain"].value_counts(dropna=True).head(25).to_dict(),
            "mean_reaction_sum": float(filtered["reaction_sum"].mean()) if len(filtered) else 0.0,
            "mean_quality_score": float(filtered["quality_score"].mean()) if len(filtered) else 0.0,
        },
    }
    return filtered, summary


def _llm_user_prompt(row: pd.Series) -> str:
    description = _safe_text(row.get("description"))
    description = description[:1600]
    source_url = _safe_text(row.get("sourceUrl"))
    currencies_list = row.get("currencies_list")
    if not isinstance(currencies_list, list):
        currencies_list = []
    currencies = ", ".join(currencies_list)
    news_datetime = row.get("newsDatetime")
    payload = {
        "title": _safe_text(row.get("title")),
        "description": description,
        "source_domain": _safe_text(row.get("sourceDomain")),
        "source_kind": _safe_text(row.get("source_kind")),
        "source_url": source_url,
        "news_datetime_utc": news_datetime.isoformat().replace("+00:00", "Z") if pd.notna(news_datetime) else None,
        "currencies": currencies,
        "reaction_sum": _safe_int(row.get("reaction_sum")),
        "engagement_sum": _safe_int(row.get("engagement_sum")),
        "important_votes": _safe_int(row.get("important")),
        "positive_votes": _safe_int(row.get("positive")),
        "negative_votes": _safe_int(row.get("negative")),
    }
    return json.dumps(payload, ensure_ascii=False)


def _score_row(row: pd.Series, *, model: str, max_retries: int = 3) -> dict[str, Any]:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0.1,
                max_completion_tokens=550,
                response_format={"type": "json_schema", "json_schema": LLM_SCHEMA},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": _llm_user_prompt(row)},
                ],
            )
            content = response.choices[0].message.content
            parsed = json.loads(content)
            return parsed
        except Exception as exc:  # pragma: no cover - exercised in live run
            last_error = exc
            if attempt >= max_retries:
                break
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"OpenAI scoring failed after {max_retries} attempts: {last_error}") from last_error


def _load_existing_scored_ids(output_jsonl: Path) -> set[int]:
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


def _scoring_output_row(row: pd.Series, llm_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "title": str(row["title"]),
        "sourceDomain": None if pd.isna(row["sourceDomain"]) else str(row["sourceDomain"]),
        "source_kind": str(row["source_kind"]),
        "sourceUrl": None if pd.isna(row["sourceUrl"]) else str(row["sourceUrl"]),
        "newsDatetime_utc": row["newsDatetime"].isoformat().replace("+00:00", "Z") if pd.notna(row["newsDatetime"]) else None,
        "research_effective_at_utc": row["research_effective_at_utc"],
        "currencies": row["currencies_list"],
        "reaction_sum": int(row["reaction_sum"]),
        "engagement_sum": int(row["engagement_sum"]),
        "quality_score": float(row["quality_score"]),
        "selection_rank": int(row["selection_rank"]),
        **llm_payload,
    }


def _strong_model_review_reasons(row: pd.Series) -> list[str]:
    reasons: list[str] = []
    repricing_type = _safe_text(row.get("repricing_type"))
    event_type = _safe_text(row.get("event_type"))
    source_kind = _safe_text(row.get("source_kind"))
    is_actionable_event = bool(row.get("is_actionable_event"))
    short_veto_flag = bool(row.get("short_veto_flag"))
    market_impact_magnitude = _safe_int(row.get("market_impact_magnitude"))

    if repricing_type in {"mixed", "unclear"}:
        reasons.append("ambiguous_repricing")
    if short_veto_flag:
        reasons.append("short_veto_guardrail")
    if source_kind == "official":
        reasons.append("official_source")
    if is_actionable_event and market_impact_magnitude >= 4:
        reasons.append("high_impact_actionable")
    if event_type == "other" and (is_actionable_event or repricing_type in {"mixed", "unclear", "real_repricing"}):
        reasons.append("generic_event_bucket")
    return reasons


def _strong_model_review_priority(reasons: list[str]) -> int:
    weights = {
        "short_veto_guardrail": 5,
        "official_source": 4,
        "ambiguous_repricing": 3,
        "high_impact_actionable": 2,
        "generic_event_bucket": 1,
    }
    return int(sum(weights.get(reason, 0) for reason in reasons))


def _build_strong_model_review_candidates(scored_frame: pd.DataFrame) -> pd.DataFrame:
    if scored_frame.empty:
        return scored_frame.copy()

    candidates = scored_frame.copy()
    candidates["strong_model_review_reasons"] = candidates.apply(_strong_model_review_reasons, axis=1)
    candidates["strong_model_review_reason_count"] = candidates["strong_model_review_reasons"].map(len)
    candidates["strong_model_review_priority"] = candidates["strong_model_review_reasons"].map(_strong_model_review_priority)
    candidates = candidates.loc[candidates["strong_model_review_reason_count"].gt(0)].copy()
    if candidates.empty:
        return candidates

    candidates = candidates.sort_values(
        [
            "strong_model_review_priority",
            "quality_score",
            "reaction_sum",
            "selection_rank",
            "id",
        ],
        ascending=[False, False, False, True, True],
    ).reset_index(drop=True)
    candidates["strong_model_review_rank"] = range(1, len(candidates) + 1)
    return candidates


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-repo-root", type=Path, default=_default_repo_root())
    parser.add_argument("--dataset-repo-url", default=DEFAULT_DATASET_REPO_URL)
    parser.add_argument("--as-of", default=datetime.now(UTC).date().isoformat())
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--min-year", type=int, default=DEFAULT_MIN_YEAR)
    parser.add_argument("--min-reaction-sum", type=int, default=DEFAULT_MIN_REACTION_SUM)
    parser.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--score-all", action="store_true")
    parser.add_argument("--include-social", action="store_true")
    parser.add_argument("--force-reextract", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required")

    dataset_repo_root = args.dataset_repo_root.expanduser().resolve()
    _ensure_repo(dataset_repo_root, repo_url=args.dataset_repo_url)

    joined_archive = dataset_repo_root / "csvOutput" / "news_currencies_source_joinedResult.rar"
    if not joined_archive.exists():
        raise FileNotFoundError(f"missing joined archive: {joined_archive}")

    output_root = ROOT / "artifacts" / "quant_research" / "datasets" / f"{args.as_of}-crypto-news-dataset"
    extracted_root = output_root / "_extracted"
    joined_csv = extracted_root / "news_currencies_source_joinedResult.csv"
    if args.force_reextract or not joined_csv.exists():
        _extract_rar_member(joined_archive, extracted_root)

    dataset_frame, prep_summary = _prepare_dataset(
        joined_csv,
        min_year=args.min_year,
        min_reaction_sum=args.min_reaction_sum,
        exclude_social=not args.include_social,
    )

    output_root.mkdir(parents=True, exist_ok=True)
    cleaned_parquet = output_root / "high_quality_crypto_news.parquet"
    cleaned_csv = output_root / "high_quality_crypto_news.csv.gz"
    scoring_input_csv = output_root / "llm_scoring_input.csv.gz"
    scored_jsonl = output_root / "llm_structured_scores.jsonl"
    scored_parquet = output_root / "llm_structured_scores.parquet"
    strong_review_csv = output_root / "strong_model_review_candidates.csv.gz"
    strong_review_parquet = output_root / "strong_model_review_candidates.parquet"
    report_json = output_root / "processing_report.json"
    state_json = output_root / "scoring_state.json"

    dataset_frame.to_parquet(cleaned_parquet, index=False)
    dataset_frame.to_csv(cleaned_csv, index=False, compression="gzip")

    if args.score_all:
        scoring_subset = dataset_frame.copy()
    else:
        scoring_subset = dataset_frame.head(max(int(args.max_rows), 0)).copy()
    scoring_subset.to_csv(scoring_input_csv, index=False, compression="gzip")

    existing_ids = _load_existing_scored_ids(scored_jsonl)
    pending_rows = [row for _, row in scoring_subset.iterrows() if int(row["id"]) not in existing_ids]

    completed_payloads: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []
    if pending_rows:
        with ThreadPoolExecutor(max_workers=max(1, int(args.max_workers))) as executor:
            futures = {executor.submit(_score_row, row, model=args.model): row for row in pending_rows}
            for future in tqdm(as_completed(futures), total=len(futures), desc="LLM scoring", unit="article"):
                row = futures[future]
                try:
                    llm_payload = future.result()
                    completed_payloads.append(_scoring_output_row(row, llm_payload))
                    if len(completed_payloads) >= 10:
                        _append_jsonl(scored_jsonl, completed_payloads)
                        existing_ids.update(int(item["id"]) for item in completed_payloads)
                        completed_payloads = []
                except Exception as exc:  # pragma: no cover - exercised in live run
                    error_rows.append(
                        {
                            "id": int(row["id"]),
                            "title": str(row["title"]),
                            "error": str(exc),
                        }
                    )
        if completed_payloads:
            _append_jsonl(scored_jsonl, completed_payloads)

    scored_rows: list[dict[str, Any]] = []
    if scored_jsonl.exists():
        for raw_line in scored_jsonl.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if line:
                scored_rows.append(json.loads(line))
    scored_frame = pd.DataFrame(scored_rows)
    if not scored_frame.empty:
        scored_frame = scored_frame.sort_values(["selection_rank", "id"]).reset_index(drop=True)
        scored_frame.to_parquet(scored_parquet, index=False)

    strong_review_candidates = _build_strong_model_review_candidates(scored_frame)
    if strong_review_candidates.empty:
        if strong_review_parquet.exists():
            strong_review_parquet.unlink()
        if strong_review_csv.exists():
            strong_review_csv.unlink()
    else:
        strong_review_candidates.to_parquet(strong_review_parquet, index=False)
        strong_review_candidates.to_csv(strong_review_csv, index=False, compression="gzip")

    strong_review_reason_counts: dict[str, int] = {}
    if not strong_review_candidates.empty:
        exploded_reasons = strong_review_candidates["strong_model_review_reasons"].explode().dropna()
        strong_review_reason_counts = {str(key): int(value) for key, value in exploded_reasons.value_counts().to_dict().items()}

    summary = {
        "contract_version": CARD_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_dataset": {
            "repo_url": args.dataset_repo_url,
            "repo_root": portable_path(dataset_repo_root),
            "joined_csv_path": portable_path(joined_csv),
        },
        "processing_parameters": {
            "model": args.model,
            "min_year": int(args.min_year),
            "min_reaction_sum": int(args.min_reaction_sum),
            "max_rows": int(args.max_rows),
            "max_workers": int(args.max_workers),
            "score_all": bool(args.score_all),
            "include_social": bool(args.include_social),
        },
        "dataset_summary": prep_summary,
        "llm_scoring": {
            "requested_rows": int(len(scoring_subset)),
            "scored_rows": int(len(scored_frame)),
            "pending_rows": int(max(len(scoring_subset) - len(scored_frame), 0)),
            "error_rows": error_rows,
            "news_kind_counts": scored_frame["news_kind"].value_counts().to_dict() if not scored_frame.empty else {},
            "event_type_counts": scored_frame["event_type"].value_counts().to_dict() if not scored_frame.empty else {},
            "repricing_type_counts": scored_frame["repricing_type"].value_counts().to_dict() if not scored_frame.empty else {},
            "short_veto_rate": float(scored_frame["short_veto_flag"].mean()) if not scored_frame.empty else 0.0,
            "mean_market_impact_magnitude": float(scored_frame["market_impact_magnitude"].mean()) if not scored_frame.empty else 0.0,
        },
        "strong_model_review_candidates": {
            "candidate_rows": int(len(strong_review_candidates)),
            "candidate_rate": float(len(strong_review_candidates) / len(scored_frame)) if len(scored_frame) else 0.0,
            "reason_counts": strong_review_reason_counts,
            "priority_counts": strong_review_candidates["strong_model_review_priority"].value_counts().to_dict() if not strong_review_candidates.empty else {},
            "top_event_types": strong_review_candidates["event_type"].value_counts().head(15).to_dict() if not strong_review_candidates.empty else {},
        },
        "artifacts": {
            "cleaned_parquet": portable_path(cleaned_parquet),
            "cleaned_csv_gz": portable_path(cleaned_csv),
            "scoring_input_csv_gz": portable_path(scoring_input_csv),
            "scored_jsonl": portable_path(scored_jsonl),
            "scored_parquet": portable_path(scored_parquet) if scored_parquet.exists() else None,
            "strong_model_review_candidates_csv_gz": portable_path(strong_review_csv) if strong_review_csv.exists() else None,
            "strong_model_review_candidates_parquet": portable_path(strong_review_parquet) if strong_review_parquet.exists() else None,
            "state_json": portable_path(state_json),
        },
    }
    write_json(report_json, summary)
    write_json(
        state_json,
        {
            "contract_version": CARD_CONTRACT_VERSION,
            "generated_at_utc": summary["generated_at_utc"],
            "scored_ids": sorted(int(value) for value in scored_frame["id"].tolist()) if not scored_frame.empty else [],
            "error_rows": error_rows,
            "strong_model_review_candidate_ids": (
                sorted(int(value) for value in strong_review_candidates["id"].tolist())
                if not strong_review_candidates.empty
                else []
            ),
        },
    )

    print(f"cleaned_rows={len(dataset_frame)}")
    print(f"scoring_requested={len(scoring_subset)}")
    print(f"scoring_completed={len(scored_frame)}")
    print(f"strong_review_candidates={len(strong_review_candidates)}")
    print(f"output_root={output_root}")


if __name__ == "__main__":
    main()
