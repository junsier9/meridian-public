from __future__ import annotations

import hashlib
import json
import os
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

from enhengclaw.agents.execution._shared import (
    SliceCompilerArtifacts,
    SliceCompilerTransportError,
    assistant_text_from_chat_completion,
    fingerprint_transcript_payload,
    openai_compatible_compile,
    try_parse_assistant_json,
)

from .contracts import QuantUniverseCandidate, read_json, utc_now, write_json
from .governance import (
    COMPLEXITY_TIERS,
    PROPOSAL_BUDGET_LIMIT,
    RUNTIME_EVOLUTION_FLAGS,
    SEARCH_ACTIONS,
    build_strategy_catalog_payload,
    normalize_proposal_spec,
    proposal_ranking_score,
    validate_proposal_spec,
)


AGENT_PROPOSAL_CONTRACT_VERSION = "quant_agent_proposal_cycle.v2"
MAX_RAW_AGENT_PROPOSALS = 40
MAX_SELECTOR_INTENTS = 12
MAX_VALIDATED_AGENT_PROPOSALS = 12
MAX_STRATEGY_LIBRARY_EXCERPT = 24
MAX_RECENT_ALPHA_EXCERPT = 6
MAX_UNIVERSE_EXCERPT = 20
SELECTOR_REQUEST_CHAR_BUDGET = 14_000
COMPILER_REQUEST_CHAR_BUDGET = 16_000
SELECTOR_MAX_COMPLETION_TOKENS = 1200
COMPILER_MAX_COMPLETION_TOKENS = 2500
JSON_OBJECT_RESPONSE_FORMAT = {"type": "json_object"}
SELECTOR_STAGE = "selector"
COMPILER_STAGE = "compiler"
PATCH_KINDS = ("none", "family_registry_patch", "feature_registry_patch")


def generate_agent_weekly_proposals(
    *,
    week_of: str,
    artifacts_root: Path,
    review_root: Path,
    strategy_library: dict[str, Any],
    universe_candidates: tuple[QuantUniverseCandidate, ...],
    registry_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cycle_root = review_root / "agent_proposals"
    cycle_root.mkdir(parents=True, exist_ok=True)
    summary_path = cycle_root / "agent_proposal_summary.json"
    transcript_path = cycle_root / "agent_proposal_transcript.json"
    selector_transcript_path = cycle_root / "selector_transcript.json"
    compiler_transcript_path = cycle_root / "compiler_transcript.json"

    prompt_payload = _prompt_payload(
        week_of=week_of,
        artifacts_root=artifacts_root,
        strategy_library=strategy_library,
        universe_candidates=universe_candidates,
        registry_snapshot=registry_snapshot,
    )
    config = _resolve_backend_config()
    prompt_fingerprint = _fingerprint(_public_prompt_payload(prompt_payload))
    selector_stage = _empty_stage_state(stage=SELECTOR_STAGE)
    compiler_stage = _empty_stage_state(stage=COMPILER_STAGE)
    selector_transcript: dict[str, Any] | None = None
    compiler_transcript: dict[str, Any] | None = None

    if not config["enabled"]:
        summary = _finalize_summary(
            status="degraded_no_api",
            success=False,
            week_of=week_of,
            cycle_root=cycle_root,
            prompt_fingerprint=prompt_fingerprint,
            selector_stage=selector_stage,
            compiler_stage=compiler_stage,
            raw_proposals=[],
            validated=[],
            quarantined=[],
            notes=[config["reason"]],
            transcript_path=None,
        )
        write_json(summary_path, summary)
        summary["summary_path"] = str(summary_path)
        return summary

    selector_request = _build_selector_stage_request(prompt_payload=prompt_payload, model_name=str(config["model_name"]))
    if selector_request["budget_status"] != "within_budget":
        selector_stage = _blocked_stage_state(
            stage_request=selector_request,
            blocked_reason="blocked_context_budget_exceeded",
            notes=["selector prompt exceeded request budget after deterministic trimming"],
        )
        summary = _finalize_summary(
            status="blocked_context_budget_exceeded",
            success=False,
            week_of=week_of,
            cycle_root=cycle_root,
            prompt_fingerprint=prompt_fingerprint,
            selector_stage=selector_stage,
            compiler_stage=compiler_stage,
            raw_proposals=[],
            validated=[],
            quarantined=[],
            notes=list(selector_stage["notes"]),
            transcript_path=None,
        )
        write_json(summary_path, summary)
        summary["summary_path"] = str(summary_path)
        return summary

    try:
        selector_artifacts = _run_stage_compile(
            stage_request=selector_request,
            config=config,
            failure_label="agent proposal selector",
        )
    except SliceCompilerTransportError as exc:
        selector_stage = _transport_error_stage_state(stage_request=selector_request, error=exc)
        summary = _finalize_summary(
            status="degraded_transport_error",
            success=False,
            week_of=week_of,
            cycle_root=cycle_root,
            prompt_fingerprint=prompt_fingerprint,
            selector_stage=selector_stage,
            compiler_stage=compiler_stage,
            raw_proposals=[],
            validated=[],
            quarantined=[],
            notes=list(selector_stage["notes"]),
            transcript_path=None,
        )
        write_json(summary_path, summary)
        summary["summary_path"] = str(summary_path)
        return summary

    selector_artifacts = _recover_selector_multi_payload_artifacts(selector_artifacts)
    selector_transcript = selector_artifacts.transcript_payload
    write_json(selector_transcript_path, selector_transcript)
    selector_output = dict(selector_artifacts.compiler_output or {})
    selector_payload = {}
    if selector_output.get("status") == "success":
        selector_payload = dict((selector_output.get("candidate_payloads") or [{}])[0])
    selector_notes = [str(item) for item in selector_output.get("notes", []) if str(item).strip()]
    raw_intents = selector_payload.get("proposal_intents", [])
    selector_intents = _normalize_selector_intents(raw_intents)
    selector_stage = _successful_stage_state(
        stage_request=selector_request,
        artifacts=selector_artifacts,
        transcript_path=selector_transcript_path,
        status="success" if selector_output.get("status") == "success" else "blocked",
        blocked_reason=None if selector_output.get("status") == "success" else selector_output.get("blocked_reason"),
        notes=selector_notes + [str(item) for item in selector_payload.get("notes", []) if str(item).strip()],
    )
    selector_stage["intent_count"] = len(selector_intents)
    if selector_output.get("status") != "success":
        summary = _finalize_summary(
            status="blocked",
            success=False,
            week_of=week_of,
            cycle_root=cycle_root,
            prompt_fingerprint=prompt_fingerprint,
            selector_stage=selector_stage,
            compiler_stage=compiler_stage,
            raw_proposals=[],
            validated=[],
            quarantined=[],
            notes=_combined_stage_notes(selector_stage, compiler_stage),
            transcript_path=_write_combined_transcript(
                transcript_path=transcript_path,
                week_of=week_of,
                selector_transcript=selector_transcript,
                compiler_transcript=compiler_transcript,
            ),
        )
        write_json(summary_path, summary)
        summary["summary_path"] = str(summary_path)
        return summary

    if not selector_intents:
        compiler_stage = _empty_stage_state(stage=COMPILER_STAGE, status="not_run", blocked_reason="selector_returned_no_intents")
        summary = _finalize_summary(
            status="success",
            success=True,
            week_of=week_of,
            cycle_root=cycle_root,
            prompt_fingerprint=prompt_fingerprint,
            selector_stage=selector_stage,
            compiler_stage=compiler_stage,
            raw_proposals=[],
            validated=[],
            quarantined=[],
            notes=_combined_stage_notes(selector_stage, compiler_stage),
            transcript_path=_write_combined_transcript(
                transcript_path=transcript_path,
                week_of=week_of,
                selector_transcript=selector_transcript,
                compiler_transcript=compiler_transcript,
            ),
        )
        write_json(summary_path, summary)
        summary["summary_path"] = str(summary_path)
        return summary

    compiler_request = _build_compiler_stage_request(
        prompt_payload=prompt_payload,
        selector_intents=selector_intents,
        model_name=str(config["model_name"]),
    )
    if compiler_request["budget_status"] != "within_budget":
        compiler_stage = _blocked_stage_state(
            stage_request=compiler_request,
            blocked_reason="blocked_context_budget_exceeded",
            notes=["compiler prompt exceeded request budget after deterministic trimming"],
        )
        summary = _finalize_summary(
            status="blocked_context_budget_exceeded",
            success=False,
            week_of=week_of,
            cycle_root=cycle_root,
            prompt_fingerprint=prompt_fingerprint,
            selector_stage=selector_stage,
            compiler_stage=compiler_stage,
            raw_proposals=[],
            validated=[],
            quarantined=[],
            notes=_combined_stage_notes(selector_stage, compiler_stage),
            transcript_path=_write_combined_transcript(
                transcript_path=transcript_path,
                week_of=week_of,
                selector_transcript=selector_transcript,
                compiler_transcript=compiler_transcript,
            ),
        )
        write_json(summary_path, summary)
        summary["summary_path"] = str(summary_path)
        return summary

    try:
        compiler_artifacts = _run_stage_compile(
            stage_request=compiler_request,
            config=config,
            failure_label="agent proposal compiler",
        )
    except SliceCompilerTransportError as exc:
        compiler_stage = _transport_error_stage_state(stage_request=compiler_request, error=exc)
        summary = _finalize_summary(
            status="degraded_transport_error",
            success=False,
            week_of=week_of,
            cycle_root=cycle_root,
            prompt_fingerprint=prompt_fingerprint,
            selector_stage=selector_stage,
            compiler_stage=compiler_stage,
            raw_proposals=[],
            validated=[],
            quarantined=[],
            notes=_combined_stage_notes(selector_stage, compiler_stage),
            transcript_path=_write_combined_transcript(
                transcript_path=transcript_path,
                week_of=week_of,
                selector_transcript=selector_transcript,
                compiler_transcript=compiler_transcript,
            ),
        )
        write_json(summary_path, summary)
        summary["summary_path"] = str(summary_path)
        return summary

    compiler_transcript = compiler_artifacts.transcript_payload
    write_json(compiler_transcript_path, compiler_transcript)
    compiler_output = dict(compiler_artifacts.compiler_output or {})
    compiler_payload = {}
    if compiler_output.get("status") == "success":
        compiler_payload = dict((compiler_output.get("candidate_payloads") or [{}])[0])
    compiler_notes = [str(item) for item in compiler_output.get("notes", []) if str(item).strip()]
    compiler_stage = _successful_stage_state(
        stage_request=compiler_request,
        artifacts=compiler_artifacts,
        transcript_path=compiler_transcript_path,
        status="success" if compiler_output.get("status") == "success" else "blocked",
        blocked_reason=None if compiler_output.get("status") == "success" else compiler_output.get("blocked_reason"),
        notes=compiler_notes + [str(item) for item in compiler_payload.get("notes", []) if str(item).strip()],
    )
    if compiler_output.get("status") != "success":
        summary = _finalize_summary(
            status="blocked",
            success=False,
            week_of=week_of,
            cycle_root=cycle_root,
            prompt_fingerprint=prompt_fingerprint,
            selector_stage=selector_stage,
            compiler_stage=compiler_stage,
            raw_proposals=[],
            validated=[],
            quarantined=[],
            notes=_combined_stage_notes(selector_stage, compiler_stage),
            transcript_path=_write_combined_transcript(
                transcript_path=transcript_path,
                week_of=week_of,
                selector_transcript=selector_transcript,
                compiler_transcript=compiler_transcript,
            ),
        )
        write_json(summary_path, summary)
        summary["summary_path"] = str(summary_path)
        return summary

    raw_proposals = compiler_payload.get("proposals", [])
    validated: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    seen_specs: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for index, raw in enumerate((raw_proposals if isinstance(raw_proposals, list) else [])[:MAX_RAW_AGENT_PROPOSALS], start=1):
        if not isinstance(raw, dict):
            quarantined.append({"index": index, "reason": "proposal_must_be_json_object"})
            continue
        normalized = normalize_proposal_spec(raw)
        normalized.setdefault("week_of", week_of)
        normalized.setdefault("proposal_origin", "agent")
        normalized.setdefault("source", "proposal")
        hygiene_reason = _proposal_hygiene_reason(normalized)
        if hygiene_reason is not None:
            quarantined.append(
                {
                    "index": index,
                    "proposal_id": normalized.get("proposal_id"),
                    "strategy_id": normalized.get("strategy_id"),
                    "reason": hygiene_reason,
                }
            )
            continue
        valid, reason = validate_proposal_spec(
            proposal_spec=normalized,
            artifacts_root=artifacts_root,
            registry_snapshot=registry_snapshot,
        )
        if not valid:
            quarantined.append(
                {
                    "index": index,
                    "proposal_id": normalized.get("proposal_id"),
                    "strategy_id": normalized.get("strategy_id"),
                    "reason": str(reason),
                }
            )
            continue
        spec_hash = str(normalized.get("spec_hash") or "")
        if spec_hash in seen_hashes:
            quarantined.append(
                {
                    "index": index,
                    "proposal_id": normalized.get("proposal_id"),
                    "strategy_id": normalized.get("strategy_id"),
                    "reason": "duplicate_spec_hash",
                }
            )
            continue
        normalized["ranking_score"] = proposal_ranking_score(normalized, seen_specs=seen_specs)
        seen_hashes.add(spec_hash)
        seen_specs.append(normalized)
        validated.append(normalized)

    validated.sort(
        key=lambda item: (
            float(item.get("ranking_score", 0.0)),
            float(item.get("priority_score", 0.0)),
            str(item.get("proposal_id") or ""),
        ),
        reverse=True,
    )
    validated = validated[:MAX_VALIDATED_AGENT_PROPOSALS]
    summary = _finalize_summary(
        status="success",
        success=True,
        week_of=week_of,
        cycle_root=cycle_root,
        prompt_fingerprint=prompt_fingerprint,
        selector_stage=selector_stage,
        compiler_stage=compiler_stage,
        raw_proposals=raw_proposals if isinstance(raw_proposals, list) else [],
        validated=validated,
        quarantined=quarantined,
        notes=_combined_stage_notes(selector_stage, compiler_stage),
        transcript_path=_write_combined_transcript(
            transcript_path=transcript_path,
            week_of=week_of,
            selector_transcript=selector_transcript,
            compiler_transcript=compiler_transcript,
        ),
    )
    write_json(summary_path, summary)
    summary["summary_path"] = str(summary_path)
    return summary


def _resolve_backend_config() -> dict[str, Any]:
    api_key = (
        os.environ.get("OPENCLAW_AGENT_PROPOSAL_API_KEY", "").strip()
        or os.environ.get("OPENCLAW", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )
    if not api_key:
        return {"enabled": False, "reason": "no OpenClaw/OpenAI API key configured for agent proposal cycle"}
    base_url = (
        os.environ.get("OPENCLAW_AGENT_PROPOSAL_BASE_URL", "").strip()
        or os.environ.get("OPENCLAW_BASE_URL", "").strip()
        or os.environ.get("OPENAI_BASE_URL", "").strip()
        or "https://api.openai.com/v1"
    )
    model_name = (
        os.environ.get("OPENCLAW_AGENT_PROPOSAL_MODEL", "").strip()
        or os.environ.get("OPENCLAW_MODEL", "").strip()
        or os.environ.get("OPENAI_MODEL", "").strip()
        or "gpt-4o-mini"
    )
    timeout_raw = (
        os.environ.get("OPENCLAW_AGENT_PROPOSAL_TIMEOUT_SECONDS", "").strip()
        or os.environ.get("OPENCLAW_TIMEOUT_SECONDS", "").strip()
        or "60"
    )
    try:
        timeout_seconds = float(timeout_raw)
    except ValueError:
        timeout_seconds = 60.0
    return {
        "enabled": True,
        "api_key": api_key,
        "base_url": base_url,
        "model_name": model_name,
        "timeout_seconds": timeout_seconds,
    }


def _prompt_payload(
    *,
    week_of: str,
    artifacts_root: Path,
    strategy_library: dict[str, Any],
    universe_candidates: tuple[QuantUniverseCandidate, ...],
    registry_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    alpha_registry_path = artifacts_root / "registry" / "alpha_registry.json"
    recent_bridge_summaries = [
        read_json(path)
        for path in _latest_bridge_summary_paths(artifacts_root=artifacts_root, limit=3)
    ]
    recent_discovery_summaries = [
        read_json(path)
        for path in _latest_discovery_summary_paths(artifacts_root=artifacts_root, limit=3)
    ]
    recent_bridge_summary = recent_bridge_summaries[-1] if recent_bridge_summaries else {}
    recent_discovery_summary = recent_discovery_summaries[-1] if recent_discovery_summaries else {}
    alpha_registry = read_json(alpha_registry_path) if alpha_registry_path.exists() else {"entries": []}
    recent_proposals = [
        {
            "strategy_id": str(entry.get("strategy_id") or ""),
            "shape": str(entry.get("shape") or ""),
            "strategy_profile": str(entry.get("strategy_profile") or ""),
            "subject": entry.get("subject"),
            "model_family": str(entry.get("model_family") or ""),
            "publication_status": str(entry.get("publication_status") or ""),
            "experiment_status": str(entry.get("experiment_status") or ""),
            "validation_metrics": _metric_excerpt(entry.get("validation_metrics")),
            "test_metrics": _metric_excerpt(entry.get("test_metrics")),
            "walk_forward_summary": _walk_forward_excerpt(entry.get("walk_forward")),
        }
        for entry in alpha_registry.get("entries", [])[-MAX_RECENT_ALPHA_EXCERPT:]
        if isinstance(entry, dict)
    ]
    strategy_sections = _strategy_library_sections(strategy_library)
    universe_summary = [
        {
            "subject": candidate.subject,
            "liquidity_bucket": candidate.liquidity_bucket,
            "selection_rank": candidate.selection_rank,
            "listing_age_days_as_of": candidate.listing_age_days_as_of,
        }
        for candidate in universe_candidates[:MAX_UNIVERSE_EXCERPT]
    ]
    bridge_suppressed_excerpt: list[dict[str, Any]] = []
    for bridge_summary in reversed(recent_bridge_summaries):
        for item in bridge_summary.get("suppressed_exports", []):
            if not isinstance(item, dict):
                continue
            bridge_suppressed_excerpt.append(
                {
                    "as_of": bridge_summary.get("as_of"),
                    "run_id": bridge_summary.get("run_id"),
                    "experiment_id": str(item.get("experiment_id") or ""),
                    "publication_status": str(item.get("publication_status") or ""),
                    "validation": str(item.get("validation") or ""),
                }
            )
            if len(bridge_suppressed_excerpt) >= 8:
                break
        if len(bridge_suppressed_excerpt) >= 8:
            break
    discovery_summary_excerpt = [
        {
            "as_of": summary.get("as_of", summary.get("week_of")),
            "run_id": summary.get("run_id"),
            "proposal_lane_mix": dict(summary.get("proposal_lane_mix") or {}),
            "agent_proposal_count": summary.get("agent_proposal_count"),
            "heuristic_proposal_count": summary.get("heuristic_proposal_count"),
            "quarantined_proposal_count": summary.get("quarantined_proposal_count"),
            "auto_bridged_snapshot_count": summary.get("auto_bridged_snapshot_count"),
            "openai_usage": dict(summary.get("openai_usage") or {}),
        }
        for summary in recent_discovery_summaries
        if isinstance(summary, dict)
    ]
    return {
        "as_of": week_of,
        "week_of": week_of,
        "catalog": build_strategy_catalog_payload(),
        "runtime_flags": dict(RUNTIME_EVOLUTION_FLAGS),
        "proposal_budget_limit": PROPOSAL_BUDGET_LIMIT,
        "selector_intent_cap": MAX_SELECTOR_INTENTS,
        "raw_proposal_cap": MAX_RAW_AGENT_PROPOSALS,
        "validated_proposal_cap": MAX_VALIDATED_AGENT_PROPOSALS,
        "strategy_library_excerpt": strategy_sections["core_entries"] + strategy_sections["discovery_entries"],
        "universe_excerpt": universe_summary,
        "recent_alpha_registry_excerpt": recent_proposals,
        "recent_discovery_summary_excerpt": discovery_summary_excerpt,
        "recent_weekly_summary_excerpt": {
            "as_of": recent_discovery_summary.get("as_of", recent_discovery_summary.get("week_of")),
            "run_id": recent_discovery_summary.get("run_id"),
            "agent_proposal_count": recent_discovery_summary.get("agent_proposal_count"),
            "heuristic_proposal_count": recent_discovery_summary.get("heuristic_proposal_count"),
            "quarantined_proposal_count": recent_discovery_summary.get("quarantined_proposal_count"),
            "auto_bridged_snapshot_count": recent_discovery_summary.get("auto_bridged_snapshot_count"),
        },
        "recent_bridge_summary_excerpt": [
            {
                "as_of": summary.get("as_of"),
                "run_id": summary.get("run_id"),
                "published_snapshot_count": summary.get("published_snapshot_count"),
                "staged_only_snapshot_count": summary.get("staged_only_snapshot_count"),
                "auto_bridged_snapshot_count": summary.get("auto_bridged_snapshot_count"),
            }
            for summary in recent_bridge_summaries
            if isinstance(summary, dict)
        ],
        "recent_bridge_suppressed_excerpt": bridge_suppressed_excerpt,
        "registry_snapshot_excerpt": {
            "snapshot_id": None if registry_snapshot is None else registry_snapshot.get("snapshot_id"),
            "model_family_count": 0 if registry_snapshot is None else len((registry_snapshot.get("model_families") or {}).get("entries", [])),
            "feature_family_count": 0 if registry_snapshot is None else len((registry_snapshot.get("feature_families") or {}).get("entries", [])),
        },
        "_strategy_library_core_excerpt": strategy_sections["core_entries"],
        "_strategy_library_discovery_excerpt": strategy_sections["discovery_entries"],
    }


def _latest_bridge_summary_paths(*, artifacts_root: Path, limit: int) -> list[Path]:
    return sorted((artifacts_root / "bridge_exports").glob("*/bridge_summary.json"))[-limit:]


def _latest_discovery_summary_paths(*, artifacts_root: Path, limit: int) -> list[Path]:
    discovery_paths = sorted((artifacts_root / "governance" / "discovery_runs").glob("*/*/discovery_governance_summary.json"))
    if discovery_paths:
        return discovery_paths[-limit:]
    return sorted((artifacts_root / "governance" / "weekly_reviews").glob("*/weekly_governance_summary.json"))[-limit:]


def _strategy_library_sections(strategy_library: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    raw_entries = [entry for entry in strategy_library.get("entries", []) if isinstance(entry, dict)]
    core_entries = [
        entry
        for entry in raw_entries
        if str(entry.get("lifecycle") or "") in {"active", "watch", "candidate"} or str(entry.get("source") or "") == "proposal"
    ]
    discovery_entries = [entry for entry in raw_entries if entry not in core_entries]
    selected_core = core_entries[-16:]
    selected_discovery = discovery_entries[-8:]
    return {
        "core_entries": _normalize_strategy_library_excerpt(selected_core),
        "discovery_entries": _normalize_strategy_library_excerpt(selected_discovery),
    }


def _normalize_strategy_library_excerpt(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen_strategy_ids: set[str] = set()
    for entry in reversed(entries):
        strategy_id = str(entry.get("strategy_id") or "")
        if strategy_id in seen_strategy_ids:
            continue
        seen_strategy_ids.add(strategy_id)
        deduped.append(
            {
                "strategy_id": strategy_id,
                "base_strategy_id": str(entry.get("base_strategy_id") or ""),
                "shape": str(entry.get("shape") or ""),
                "strategy_profile": str(entry.get("strategy_profile") or ""),
                "subject": entry.get("subject"),
                "model_family": str(entry.get("model_family") or ""),
                "family_id": str(entry.get("family_id") or entry.get("model_family") or ""),
                "feature_groups": list(entry.get("feature_groups") or []),
                "lifecycle": str(entry.get("lifecycle") or ""),
                "publication_status": str(entry.get("publication_status") or ""),
                "source": str(entry.get("source") or ""),
                "spec_hash": str(entry.get("spec_hash") or ""),
            }
        )
    deduped.reverse()
    return deduped[-MAX_STRATEGY_LIBRARY_EXCERPT:]


def _build_selector_stage_request(*, prompt_payload: dict[str, Any], model_name: str) -> dict[str, Any]:
    return _build_stage_request(
        stage=SELECTOR_STAGE,
        model_name=model_name,
        budget_chars=SELECTOR_REQUEST_CHAR_BUDGET,
        max_completion_tokens=SELECTOR_MAX_COMPLETION_TOKENS,
        base_context={
            "as_of": prompt_payload.get("as_of", prompt_payload.get("week_of")),
            "week_of": prompt_payload.get("week_of"),
            "catalog": prompt_payload.get("catalog"),
            "runtime_flags": prompt_payload.get("runtime_flags"),
            "proposal_budget_limit": prompt_payload.get("proposal_budget_limit"),
            "selector_intent_cap": MAX_SELECTOR_INTENTS,
            "raw_proposal_cap": prompt_payload.get("raw_proposal_cap"),
            "validated_proposal_cap": prompt_payload.get("validated_proposal_cap"),
            "recent_discovery_summary_excerpt": prompt_payload.get("recent_discovery_summary_excerpt"),
            "recent_weekly_summary_excerpt": prompt_payload.get("recent_weekly_summary_excerpt"),
            "recent_bridge_summary_excerpt": prompt_payload.get("recent_bridge_summary_excerpt"),
            "registry_snapshot_excerpt": prompt_payload.get("registry_snapshot_excerpt"),
        },
        core_entries=list(prompt_payload.get("_strategy_library_core_excerpt", [])),
        discovery_entries=list(prompt_payload.get("_strategy_library_discovery_excerpt", [])),
        recent_alpha=list(prompt_payload.get("recent_alpha_registry_excerpt", [])),
        universe=list(prompt_payload.get("universe_excerpt", [])),
        suppressed=list(prompt_payload.get("recent_bridge_suppressed_excerpt", [])),
    )


def _build_compiler_stage_request(
    *,
    prompt_payload: dict[str, Any],
    selector_intents: list[dict[str, Any]],
    model_name: str,
) -> dict[str, Any]:
    strategy_ids = {str(item.get("base_strategy_id") or "").strip() for item in selector_intents if str(item.get("base_strategy_id") or "").strip()}
    subjects = {str(item.get("subject") or "").strip().upper() for item in selector_intents if str(item.get("subject") or "").strip()}
    family_hints = {str(item.get("family_id_hint") or "").strip() for item in selector_intents if str(item.get("family_id_hint") or "").strip()}
    core_entries = [
        entry
        for entry in prompt_payload.get("_strategy_library_core_excerpt", [])
        if _strategy_entry_matches(entry=entry, strategy_ids=strategy_ids, subjects=subjects, family_hints=family_hints)
    ]
    discovery_entries = [
        entry
        for entry in prompt_payload.get("_strategy_library_discovery_excerpt", [])
        if _strategy_entry_matches(entry=entry, strategy_ids=strategy_ids, subjects=subjects, family_hints=family_hints)
    ]
    if not core_entries:
        core_entries = list(prompt_payload.get("_strategy_library_core_excerpt", []))[:6]
    if not discovery_entries:
        discovery_entries = list(prompt_payload.get("_strategy_library_discovery_excerpt", []))[:4]
    recent_alpha = [
        entry
        for entry in prompt_payload.get("recent_alpha_registry_excerpt", [])
        if _alpha_entry_matches(entry=entry, strategy_ids=strategy_ids, subjects=subjects, family_hints=family_hints)
    ]
    if not recent_alpha:
        recent_alpha = list(prompt_payload.get("recent_alpha_registry_excerpt", []))[:3]
    universe = [
        entry
        for entry in prompt_payload.get("universe_excerpt", [])
        if str(entry.get("subject") or "").strip().upper() in subjects
    ]
    if not universe:
        universe = list(prompt_payload.get("universe_excerpt", []))[:6]
    suppressed = list(prompt_payload.get("recent_bridge_suppressed_excerpt", []))[:4]
    return _build_stage_request(
        stage=COMPILER_STAGE,
        model_name=model_name,
        budget_chars=COMPILER_REQUEST_CHAR_BUDGET,
        max_completion_tokens=COMPILER_MAX_COMPLETION_TOKENS,
        base_context={
            "as_of": prompt_payload.get("as_of", prompt_payload.get("week_of")),
            "week_of": prompt_payload.get("week_of"),
            "catalog": prompt_payload.get("catalog"),
            "runtime_flags": prompt_payload.get("runtime_flags"),
            "proposal_budget_limit": prompt_payload.get("proposal_budget_limit"),
            "validated_proposal_cap": prompt_payload.get("validated_proposal_cap"),
            "selector_intents": selector_intents[:MAX_SELECTOR_INTENTS],
            "recent_discovery_summary_excerpt": prompt_payload.get("recent_discovery_summary_excerpt"),
            "recent_weekly_summary_excerpt": prompt_payload.get("recent_weekly_summary_excerpt"),
            "recent_bridge_summary_excerpt": prompt_payload.get("recent_bridge_summary_excerpt"),
            "registry_snapshot_excerpt": prompt_payload.get("registry_snapshot_excerpt"),
        },
        core_entries=core_entries,
        discovery_entries=discovery_entries,
        recent_alpha=recent_alpha,
        universe=universe,
        suppressed=suppressed,
    )


def _build_stage_request(
    *,
    stage: str,
    model_name: str,
    budget_chars: int,
    max_completion_tokens: int,
    base_context: dict[str, Any],
    core_entries: list[dict[str, Any]],
    discovery_entries: list[dict[str, Any]],
    recent_alpha: list[dict[str, Any]],
    universe: list[dict[str, Any]],
    suppressed: list[dict[str, Any]],
) -> dict[str, Any]:
    trimmed_counts = {
        "strategy_library_discovery_entries": 0,
        "recent_alpha_entries": 0,
        "universe_entries": 0,
        "bridge_suppressed_entries": 0,
    }
    while True:
        context = {
            **base_context,
            "strategy_library_excerpt": core_entries + discovery_entries,
            "recent_alpha_registry_excerpt": recent_alpha,
            "universe_excerpt": universe,
            "recent_bridge_suppressed_excerpt": suppressed,
        }
        messages = _build_messages(stage=stage, prompt_payload=context)
        prompt_context = {
            "messages": messages,
            "prompt_fingerprint": _fingerprint({"stage": stage, "messages": messages}),
            "object_context_fingerprint": _fingerprint(
                {
                    "stage": stage,
                    "week_of": base_context.get("week_of"),
                    "strategy_ids": [str(item.get("strategy_id") or "") for item in context.get("strategy_library_excerpt", [])],
                    "subjects": [str(item.get("subject") or "") for item in context.get("universe_excerpt", [])],
                }
            ),
        }
        request_body_chars = _request_body_chars(
            model_name=model_name,
            messages=messages,
            response_format=JSON_OBJECT_RESPONSE_FORMAT,
            max_completion_tokens=max_completion_tokens,
        )
        if request_body_chars <= budget_chars:
            return {
                "stage": stage,
                "messages": messages,
                "prompt_context": prompt_context,
                "request_body_chars": request_body_chars,
                "max_completion_tokens": max_completion_tokens,
                "budget_status": "within_budget",
                "trimmed_counts": trimmed_counts,
            }
        if discovery_entries:
            discovery_entries.pop(0)
            trimmed_counts["strategy_library_discovery_entries"] += 1
            continue
        if recent_alpha:
            recent_alpha.pop(0)
            trimmed_counts["recent_alpha_entries"] += 1
            continue
        if universe:
            universe.pop()
            trimmed_counts["universe_entries"] += 1
            continue
        if suppressed:
            suppressed.pop()
            trimmed_counts["bridge_suppressed_entries"] += 1
            continue
        return {
            "stage": stage,
            "messages": messages,
            "prompt_context": prompt_context,
            "request_body_chars": request_body_chars,
            "max_completion_tokens": max_completion_tokens,
            "budget_status": "blocked_context_budget_exceeded",
            "trimmed_counts": trimmed_counts,
        }


def _build_messages(*, stage: str, prompt_payload: dict[str, Any]) -> list[dict[str, str]]:
    if stage == SELECTOR_STAGE:
        instructions = {
            "task": "Select up to 12 weekly quant proposal intents for deterministic evaluation.",
            "output_contract": {
                "status": "success or blocked",
                "blocked_reason": "string or null",
                "candidate_payloads": [
                    {
                        "proposal_intents": [
                            {
                                "search_action": "feature_variant|universe_variant|new_feature_family",
                                "base_strategy_id": "string|null",
                                "subject": "string|null",
                                "family_id_hint": "string",
                                "priority_score": 0.0,
                                "complexity_tier": "low|medium|high",
                                "required_patch_kind": "none|family_registry_patch|feature_registry_patch",
                                "risk_tags": ["regime_shift"],
                                "auto_bridge_requested": True,
                                "why_now": "required",
                            }
                        ],
                        "notes": ["optional note"],
                    }
                ],
                "notes": ["optional envelope note"],
            },
            "hard_rules": [
                "Return valid JSON only.",
                "Do not wrap the JSON envelope in Markdown fences, backticks, or explanatory prose.",
                "Never emit runnable code, Python snippets, or final proposal specs in selector stage.",
                "Emit exactly one candidate_payloads object and place all selector intents inside its proposal_intents array.",
                "Emit at most one intent per opportunity and no more than 12 intents total.",
                "required_patch_kind is a hard downstream requirement, not a hint.",
            "Do not emit parameter_tune, new_model_family, or model_overlay intents.",
                "Do not emit new_feature_family intents unless the compiler can supply a non-empty registry patch.",
                "Prefer feature_variant or universe_variant when you cannot specify a valid registry patch.",
                "Set required_patch_kind to feature_registry_patch for new_feature_family.",
                "If no viable intents exist, return success with an empty proposal_intents array.",
            ],
        }
        system_prompt = (
            "You are a quant research proposal selector. Produce only a raw JSON envelope that follows the provided contract. "
            "Select intents only, not full proposal specs."
        )
    else:
        instructions = {
            "task": "Compile up to 12 weekly quant proposal specs from the shortlisted selector intents.",
            "output_contract": {
                "status": "success or blocked",
                "blocked_reason": "string or null",
                "candidate_payloads": [
                    {
                        "proposals": [
                            {
                                "proposal_id": "string",
                                "proposal_bucket": "config|feature|universe",
                                "week_of": "YYYY-MM-DD",
                                "base_strategy_id": "string|null",
                                "strategy_id": "string",
                                "shape": "single_asset|cross_sectional",
                                "strategy_profile": "conservative|balanced|aggressive",
                                "subject": "string|null",
                                "universe_filter": {},
                                "model_family": "string",
                                "feature_groups": ["core_context", "trend"],
                                "profile_constraints_override": {},
                                "rationale": "required",
                                "expected_edge": "required",
                                "invalidates_if": "required",
                                "proposal_origin": "agent",
                                "search_action": "feature_variant|universe_variant|new_feature_family",
                                "parent_spec_hash": "string|null",
                                "family_registry_patch": {"families": []},
                                "feature_registry_patch": {"families": []},
                                "priority_score": 0.0,
                                "complexity_tier": "low|medium|high",
                                "risk_tags": ["regime_shift"],
                                "auto_bridge_requested": True,
                                "family_id": "string",
                            }
                        ],
                        "notes": ["optional note"],
                    }
                ],
                "notes": ["optional envelope note"],
            },
            "hard_rules": [
                "Return valid JSON only.",
                "Do not wrap the JSON envelope in Markdown fences, backticks, or explanatory prose.",
                "Never emit runnable code or Python snippets.",
                "Emit exactly one candidate_payloads object and place all compiled proposals inside its proposals array.",
                "Compile at most one proposal per selector intent and no more than 12 proposals total.",
            "Do not emit parameter_tune, new_model_family, or model_overlay proposals.",
                "Do not emit new_feature_family proposals unless feature_registry_patch contains at least one family entry.",
                "Prefer feature_variant or universe_variant when you cannot specify a valid registry patch.",
                "For new_feature_family proposals, feature_registry_patch must contain at least one family entry.",
                "Use only engine templates linear_classifier, tree_ensemble, boosted_tree, meta_label_wrapper, deterministic_rule_stack.",
                "Use only transforms lag, difference, ratio, ema, rolling_mean, rolling_std, zscore, rank, interaction, clip.",
                "Do not exceed 32 generated features, 12 hyperparameters, or 3 interaction features per proposal.",
                "Avoid future-looking or target-derived features.",
            ],
            "patch_examples": {
                "family_registry_patch": {
                    "families": [
                        {
                            "family_id": "adaptive_tree_stack",
                            "engine_template": "tree_ensemble",
                            "allowed_shapes": ["single_asset"],
                            "hyperparameters": {"max_depth": 4},
                        }
                    ]
                },
                "feature_registry_patch": {
                    "families": [
                        {
                            "family_id": "adaptive_momentum_bundle",
                            "transforms": [
                                {"transform": "ema", "source": "close", "window": 21},
                            ],
                        }
                    ]
                },
            },
        }
        system_prompt = (
            "You are a quant research proposal compiler. Produce only a raw JSON envelope that follows the provided contract, "
            "with no Markdown fences or commentary."
        )
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "instructions": instructions,
                    "context": prompt_payload,
                },
                ensure_ascii=True,
                sort_keys=True,
            ),
        },
    ]


def _run_stage_compile(
    *,
    stage_request: dict[str, Any],
    config: dict[str, Any],
    failure_label: str,
) -> SliceCompilerArtifacts:
    return openai_compatible_compile(
        base_url=config["base_url"],
        model_name=config["model_name"],
        api_key=config["api_key"],
        timeout_seconds=config["timeout_seconds"],
        backend_kind="openai_compatible",
        backend_name=str(config["model_name"]),
        contract_version=AGENT_PROPOSAL_CONTRACT_VERSION,
        failure_label=failure_label,
        observation_fingerprint=str(stage_request["prompt_context"]["prompt_fingerprint"]),
        prompt_context=stage_request["prompt_context"],
        response_format=JSON_OBJECT_RESPONSE_FORMAT,
        max_completion_tokens=int(stage_request["max_completion_tokens"]),
        request_metadata={"stage": stage_request["stage"]},
        allow_retry_without_response_format=True,
    )


def _recover_selector_multi_payload_artifacts(artifacts: SliceCompilerArtifacts) -> SliceCompilerArtifacts:
    compiler_output = dict(getattr(artifacts, "compiler_output", {}) or {})
    if compiler_output.get("blocked_reason") != "model_must_emit_exactly_one_candidate_payload":
        return artifacts
    raw_model_output = dict(getattr(artifacts, "raw_model_output", {}) or {})
    assistant_text = str(raw_model_output.get("assistant_text") or "").strip()
    if not assistant_text:
        assistant_text = assistant_text_from_chat_completion(raw_model_output.get("response_json")).strip()
    if not assistant_text:
        return artifacts
    assistant_payload, assistant_parse_error, parse_recovery_notes = try_parse_assistant_json(assistant_text)
    if assistant_parse_error is not None or not isinstance(assistant_payload, dict):
        return artifacts
    if str(assistant_payload.get("status", "")).strip().lower() != "success":
        return artifacts
    raw_candidate_payloads = assistant_payload.get("candidate_payloads", [])
    if not isinstance(raw_candidate_payloads, list):
        return artifacts
    candidate_payloads = [dict(item) for item in raw_candidate_payloads if isinstance(item, dict)]
    if len(candidate_payloads) <= 1:
        return artifacts
    merged_intents: list[dict[str, Any]] = []
    merged_notes: list[str] = []
    for payload in candidate_payloads:
        proposal_intents = payload.get("proposal_intents", [])
        if isinstance(proposal_intents, list):
            merged_intents.extend(item for item in proposal_intents if isinstance(item, dict))
        payload_notes = payload.get("notes", [])
        if isinstance(payload_notes, list):
            merged_notes.extend(str(item) for item in payload_notes if str(item).strip())
    recovered_output = {
        "status": "success",
        "blocked_reason": None,
        "candidate_payloads": [
            {
                "proposal_intents": merged_intents,
                "notes": merged_notes,
            }
        ],
        "notes": [
            *parse_recovery_notes,
            *[str(item) for item in assistant_payload.get("notes", []) if str(item).strip()],
            f"selector_candidate_payloads_merged:{len(candidate_payloads)}",
        ],
    }
    transcript_payload = dict(getattr(artifacts, "transcript_payload", {}) or {})
    if transcript_payload:
        transcript_payload["compiler_output"] = recovered_output
        transcript_payload["transcript_fingerprint"] = fingerprint_transcript_payload(transcript_payload)
    if isinstance(artifacts, SliceCompilerArtifacts):
        return replace(artifacts, compiler_output=recovered_output, transcript_payload=transcript_payload)
    try:
        artifacts.compiler_output = recovered_output
        artifacts.transcript_payload = transcript_payload
    except (AttributeError, FrozenInstanceError, TypeError):
        return artifacts
    return artifacts


def _normalize_selector_intents(raw_intents: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_intents, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_intents:
        if not isinstance(raw, dict):
            continue
        search_action = str(raw.get("search_action") or "").strip()
        if search_action not in SEARCH_ACTIONS:
            continue
        if search_action == "model_overlay":
            continue
        try:
            priority_score = float(raw.get("priority_score", 0.0) or 0.0)
        except (TypeError, ValueError):
            priority_score = 0.0
        complexity_tier = str(raw.get("complexity_tier") or "medium").strip().lower() or "medium"
        if complexity_tier not in COMPLEXITY_TIERS:
            complexity_tier = "medium"
        required_patch_kind = str(raw.get("required_patch_kind") or "").strip() or _required_patch_kind_for_action(search_action)
        if required_patch_kind not in PATCH_KINDS:
            required_patch_kind = _required_patch_kind_for_action(search_action)
        why_now = str(raw.get("why_now") or "").strip()
        if not why_now:
            continue
        risk_tags = [str(item).strip() for item in raw.get("risk_tags", []) if str(item).strip()]
        normalized_intent = {
            "search_action": search_action,
            "base_strategy_id": str(raw.get("base_strategy_id") or "").strip() or None,
            "subject": str(raw.get("subject") or "").strip().upper() or None,
            "family_id_hint": str(raw.get("family_id_hint") or raw.get("family_id") or raw.get("model_family") or "").strip() or "unknown",
            "priority_score": round(priority_score, 4),
            "complexity_tier": complexity_tier,
            "required_patch_kind": required_patch_kind,
            "risk_tags": risk_tags,
            "auto_bridge_requested": bool(raw.get("auto_bridge_requested", False)),
            "why_now": why_now,
        }
        intent_fingerprint = _fingerprint(normalized_intent)
        if intent_fingerprint in seen:
            continue
        seen.add(intent_fingerprint)
        normalized.append(normalized_intent)
    normalized.sort(
        key=lambda item: (
            float(item.get("priority_score", 0.0)),
            -float(COMPLEXITY_TIERS.get(str(item.get("complexity_tier") or "medium"), 0.5)),
            str(item.get("family_id_hint") or ""),
            str(item.get("subject") or ""),
        ),
        reverse=True,
    )
    return normalized[:MAX_SELECTOR_INTENTS]


def _required_patch_kind_for_action(search_action: str) -> str:
    if search_action == "new_model_family":
        return "family_registry_patch"
    if search_action == "new_feature_family":
        return "feature_registry_patch"
    return "none"


def _proposal_hygiene_reason(proposal_spec: dict[str, Any]) -> str | None:
    search_action = str(proposal_spec.get("search_action") or "").strip()
    if search_action == "model_overlay":
        return "model_overlay proposals are reserved for heuristic/internal discovery only"
    if search_action == "new_model_family" and not _patch_has_families(proposal_spec.get("family_registry_patch")):
        return "new_model_family proposals must include family_registry_patch"
    if search_action == "new_feature_family" and not _patch_has_families(proposal_spec.get("feature_registry_patch")):
        return "new_feature_family proposals must include feature_registry_patch"
    return None


def _patch_has_families(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    families = value.get("families", [])
    return isinstance(families, list) and any(isinstance(item, dict) for item in families)


def _strategy_entry_matches(
    *,
    entry: dict[str, Any],
    strategy_ids: set[str],
    subjects: set[str],
    family_hints: set[str],
) -> bool:
    strategy_id = str(entry.get("strategy_id") or "").strip()
    base_strategy_id = str(entry.get("base_strategy_id") or "").strip()
    subject = str(entry.get("subject") or "").strip().upper()
    family_id = str(entry.get("family_id") or entry.get("model_family") or "").strip()
    return (
        strategy_id in strategy_ids
        or base_strategy_id in strategy_ids
        or (subject and subject in subjects)
        or (family_id and family_id in family_hints)
    )


def _alpha_entry_matches(
    *,
    entry: dict[str, Any],
    strategy_ids: set[str],
    subjects: set[str],
    family_hints: set[str],
) -> bool:
    strategy_id = str(entry.get("strategy_id") or "").strip()
    subject = str(entry.get("subject") or "").strip().upper()
    model_family = str(entry.get("model_family") or "").strip()
    return strategy_id in strategy_ids or (subject and subject in subjects) or (model_family and model_family in family_hints)


def _request_body_chars(
    *,
    model_name: str,
    messages: list[dict[str, str]],
    response_format: dict[str, Any] | None,
    max_completion_tokens: int | None,
) -> int:
    request_body: dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "temperature": 0.0,
    }
    if response_format:
        request_body["response_format"] = dict(response_format)
    if max_completion_tokens is not None:
        request_body["max_completion_tokens"] = int(max_completion_tokens)
    return len(json.dumps(request_body))


def _empty_stage_state(stage: str, *, status: str = "not_run", blocked_reason: str | None = None) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": status,
        "blocked_reason": blocked_reason,
        "prompt_fingerprint": None,
        "request_body_chars": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "latency_ms": 0,
        "retry_count": 0,
        "fallback_without_response_format": False,
        "budget_status": "not_built",
        "trimmed_counts": {
            "strategy_library_discovery_entries": 0,
            "recent_alpha_entries": 0,
            "universe_entries": 0,
            "bridge_suppressed_entries": 0,
        },
        "notes": [],
        "transcript_path": None,
    }


def _successful_stage_state(
    *,
    stage_request: dict[str, Any],
    artifacts: SliceCompilerArtifacts,
    transcript_path: Path,
    status: str,
    blocked_reason: str | None,
    notes: list[str],
) -> dict[str, Any]:
    usage = dict((artifacts.raw_model_output.get("response_json") or {}).get("usage") or {})
    model_request = dict(getattr(artifacts, "model_request", {}) or {})
    return {
        "stage": stage_request["stage"],
        "status": status,
        "blocked_reason": blocked_reason,
        "prompt_fingerprint": stage_request["prompt_context"]["prompt_fingerprint"],
        "request_body_chars": int(model_request.get("request_body_chars", stage_request.get("request_body_chars", 0)) or 0),
        "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
        "total_tokens": int(usage.get("total_tokens", 0) or 0),
        "usage": {
            "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
            "total_tokens": int(usage.get("total_tokens", 0) or 0),
        },
        "latency_ms": int(model_request.get("latency_ms", 0) or 0),
        "retry_count": int(model_request.get("retry_count", 0) or 0),
        "fallback_without_response_format": bool(model_request.get("fallback_without_response_format", False)),
        "budget_status": stage_request.get("budget_status", "within_budget"),
        "trimmed_counts": dict(stage_request.get("trimmed_counts") or {}),
        "notes": _stage_notes(stage_request=stage_request, extra_notes=notes),
        "transcript_path": str(transcript_path),
    }


def _transport_error_stage_state(
    *,
    stage_request: dict[str, Any],
    error: SliceCompilerTransportError,
) -> dict[str, Any]:
    details = dict(error.details or {})
    return {
        "stage": stage_request["stage"],
        "status": "degraded_transport_error",
        "blocked_reason": "degraded_transport_error",
        "prompt_fingerprint": stage_request["prompt_context"]["prompt_fingerprint"],
        "request_body_chars": int(details.get("request_body_chars", stage_request.get("request_body_chars", 0)) or 0),
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "latency_ms": int(details.get("latency_ms", 0) or 0),
        "retry_count": int(details.get("retry_count", 0) or 0),
        "fallback_without_response_format": bool(details.get("fallback_without_response_format", False)),
        "budget_status": stage_request.get("budget_status", "within_budget"),
        "trimmed_counts": dict(stage_request.get("trimmed_counts") or {}),
        "notes": _stage_notes(stage_request=stage_request, extra_notes=[str(error)]),
        "transcript_path": None,
    }


def _blocked_stage_state(
    *,
    stage_request: dict[str, Any],
    blocked_reason: str,
    notes: list[str],
) -> dict[str, Any]:
    stage_state = _empty_stage_state(stage_request["stage"], status="blocked", blocked_reason=blocked_reason)
    stage_state["prompt_fingerprint"] = stage_request["prompt_context"]["prompt_fingerprint"]
    stage_state["request_body_chars"] = int(stage_request.get("request_body_chars", 0) or 0)
    stage_state["budget_status"] = stage_request.get("budget_status", "within_budget")
    stage_state["trimmed_counts"] = dict(stage_request.get("trimmed_counts") or {})
    stage_state["notes"] = _stage_notes(stage_request=stage_request, extra_notes=notes)
    return stage_state


def _stage_notes(*, stage_request: dict[str, Any], extra_notes: list[str]) -> list[str]:
    notes = [str(item) for item in extra_notes if str(item).strip()]
    trimmed_counts = dict(stage_request.get("trimmed_counts") or {})
    trimmed_summary = ", ".join(
        f"{key}={value}"
        for key, value in trimmed_counts.items()
        if int(value or 0) > 0
    )
    if trimmed_summary:
        notes.append(f"context_trimmed[{stage_request['stage']}]: {trimmed_summary}")
    return notes


def _write_combined_transcript(
    *,
    transcript_path: Path,
    week_of: str,
    selector_transcript: dict[str, Any] | None,
    compiler_transcript: dict[str, Any] | None,
) -> str | None:
    if selector_transcript is None and compiler_transcript is None:
        return None
    payload = {
        "generated_at_utc": utc_now(),
        "week_of": week_of,
        "contract_version": AGENT_PROPOSAL_CONTRACT_VERSION,
        "stages": {
            "selector": selector_transcript,
            "compiler": compiler_transcript,
        },
    }
    write_json(transcript_path, payload)
    return str(transcript_path)


def _finalize_summary(
    *,
    status: str,
    success: bool,
    week_of: str,
    cycle_root: Path,
    prompt_fingerprint: str,
    selector_stage: dict[str, Any],
    compiler_stage: dict[str, Any],
    raw_proposals: list[Any],
    validated: list[dict[str, Any]],
    quarantined: list[dict[str, Any]],
    notes: list[str],
    transcript_path: str | None,
) -> dict[str, Any]:
    parsed_proposal_count = len([item for item in raw_proposals if isinstance(item, dict)])
    quarantine_reason_counts = _quarantine_reason_counts(quarantined)
    total_prompt_tokens = int(selector_stage.get("prompt_tokens", 0) or 0) + int(compiler_stage.get("prompt_tokens", 0) or 0)
    total_completion_tokens = int(selector_stage.get("completion_tokens", 0) or 0) + int(compiler_stage.get("completion_tokens", 0) or 0)
    return {
        "generated_at_utc": utc_now(),
        "week_of": week_of,
        "status": status,
        "success": success,
        "cycle_root": str(cycle_root),
        "prompt_fingerprint": prompt_fingerprint,
        "requested_raw_proposal_cap": MAX_RAW_AGENT_PROPOSALS,
        "validated_proposal_cap": MAX_VALIDATED_AGENT_PROPOSALS,
        "runtime_flags": dict(RUNTIME_EVOLUTION_FLAGS),
        "selector": selector_stage,
        "compiler": compiler_stage,
        "prompt_budget_status": {
            SELECTOR_STAGE: selector_stage.get("budget_status"),
            COMPILER_STAGE: compiler_stage.get("budget_status"),
        },
        "raw_proposal_count": len(raw_proposals),
        "compiler_extracted_proposal_count": len(raw_proposals),
        "parsed_proposal_count": parsed_proposal_count,
        "validated_proposal_count": len(validated),
        "quarantined_proposal_count": len(quarantined),
        "compiler_hygiene_quarantine_count": len(quarantined),
        "quarantine_reason_counts": quarantine_reason_counts,
        "parse_success_rate": _safe_rate(numerator=parsed_proposal_count, denominator=len(raw_proposals) if raw_proposals else 0),
        "quarantine_rate": _safe_rate(numerator=len(quarantined), denominator=len(raw_proposals)),
        "api_failure_rate": 1.0 if status == "degraded_transport_error" else 0.0,
        "usage": {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_prompt_tokens + total_completion_tokens,
        },
        "compiler_status": compiler_stage.get("status"),
        "compiler_blocked_reason": compiler_stage.get("blocked_reason"),
        "selector_status": selector_stage.get("status"),
        "selector_blocked_reason": selector_stage.get("blocked_reason"),
        "selector_usage": dict(selector_stage.get("usage") or {}),
        "compiler_usage": dict(compiler_stage.get("usage") or {}),
        "response_format_fallback_count": int(bool(selector_stage.get("fallback_without_response_format")))
        + int(bool(compiler_stage.get("fallback_without_response_format"))),
        "notes": list(dict.fromkeys(str(item) for item in notes if str(item).strip())),
        "validated_proposals": validated,
        "quarantined_proposals": quarantined,
        "transcript_path": transcript_path,
    }


def _combined_stage_notes(selector_stage: dict[str, Any], compiler_stage: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    notes.extend(str(item) for item in selector_stage.get("notes", []) if str(item).strip())
    notes.extend(str(item) for item in compiler_stage.get("notes", []) if str(item).strip())
    return notes


def _quarantine_reason_counts(quarantined: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in quarantined:
        reason = str(item.get("reason") or "").strip()
        if not reason:
            continue
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _public_prompt_payload(prompt_payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in prompt_payload.items() if not str(key).startswith("_")}


def _metric_excerpt(value: Any) -> dict[str, Any]:
    metrics = dict(value or {}) if isinstance(value, dict) else {}
    return {
        "net_return": metrics.get("net_return"),
        "sharpe": metrics.get("sharpe"),
        "max_drawdown": metrics.get("max_drawdown"),
    }


def _walk_forward_excerpt(value: Any) -> dict[str, Any]:
    walk_forward = dict(value or {}) if isinstance(value, dict) else {}
    return {
        "median_oos_sharpe": walk_forward.get("median_oos_sharpe"),
        "window_count": walk_forward.get("window_count"),
    }


def _fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _safe_rate(*, numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)
