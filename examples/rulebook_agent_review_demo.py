from __future__ import annotations

import argparse
from dataclasses import asdict
from importlib import import_module
import json
from pathlib import Path
import sys

from _canonical_demo_support import governed_demo_session_path, resolve_governed_demo_artifacts_root
from enhengclaw.agents import definitions as agent_definitions_module
from enhengclaw.agents.owner_state import (
    BacklogItem,
    FinalOutputRecord,
    IntermediateFinding,
    OwnerArtifactWriter,
    OwnerWorkSpec,
    ReviewArtifactRecord,
    VerificationItem,
)
from enhengclaw.core.claims import Claim, EvidenceRef
from enhengclaw.core.enums import (
    ClaimStatus,
    ClaimType,
    Direction,
    EvidenceLevel,
    ObjectType,
    ProcessingState,
    RiskState,
    SourceFamily,
    TimeHorizon,
)
from enhengclaw.core.research_object import ResearchObject
from enhengclaw.core.session import FileObjectStore, RuntimeSession
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run read-only rulebook-agent review demos against a seeded runtime session."
    )
    subparsers = parser.add_subparsers(dest="command")
    for agent_definition in _review_surface_definitions():
        agent_id = str(agent_definition["agent_id"])
        subparser = subparsers.add_parser(
            agent_id,
            help=f"Run the read-only {agent_id} demo against one seeded runtime session.",
        )
        subparser.add_argument("--artifacts-root", default=None)
        subparser.add_argument("--object-id", default=f"{agent_id}-aix")
        subparser.add_argument("--subject", default="AIX")
        subparser.add_argument("--scope", default="spot+perp")
        subparser.set_defaults(agent_definition=agent_definition, func=_run_readonly_demo)
    return parser


def _run_readonly_demo(args: argparse.Namespace) -> dict[str, object]:
    agent_definition = dict(args.agent_definition)
    agent_id = str(agent_definition["agent_id"])
    review_surface_definition = dict(agent_definition["operator_review_surface"])
    inspect = _load_callable(str(review_surface_definition["tool"]))
    review_surface = _review_surface_name(str(review_surface_definition["tool"]))
    artifacts_root = resolve_governed_demo_artifacts_root(artifacts_root=args.artifacts_root, agent_id=agent_id)
    owner_store = OwnerArtifactWriter(Path(artifacts_root).resolve() / "agent_review_demo")
    run_id = f"{agent_id}-review-{args.object_id}"
    owner_store.write_spec(
        OwnerWorkSpec(
            run_id=run_id,
            owner_agent_id="rulebook_owner",
            requested_delegate_id=agent_id,
            object_id=args.object_id,
            subject=args.subject,
            scope=args.scope,
            user_intent=f"Run the read-only review surface for '{agent_id}'.",
            constraints=("readonly_review", "no_runtime_mutation"),
        )
    )
    owner_store.write_backlog(
        run_id,
        [
            BacklogItem("capture_spec", "Capture explicit request spec", "done", "rulebook_owner"),
            BacklogItem("seed_session", "Seed or reuse review session", "pending", "rulebook_owner"),
            BacklogItem("run_review", "Execute read-only review surface", "pending", "rulebook_owner"),
            BacklogItem("finalize", "Persist final review output", "pending", "rulebook_owner"),
        ],
    )
    session_path = governed_demo_session_path(artifacts_root=artifacts_root, object_id=args.object_id)
    if not session_path.exists():
        _seed_review_session(
            artifacts_root=artifacts_root,
            object_id=args.object_id,
            subject=args.subject,
            scope=args.scope,
        )
        seed_action = "seeded"
    else:
        seed_action = "reused"
    runtime = RuntimeOrchestrator(store=FileObjectStore(Path(artifacts_root).resolve() / "runtime_sessions"))
    before = session_path.read_text(encoding="utf-8")
    review = inspect(runtime=runtime, object_id=args.object_id)
    after = session_path.read_text(encoding="utf-8")
    owner_store.write_backlog(
        run_id,
        [
            BacklogItem("capture_spec", "Capture explicit request spec", "done", "rulebook_owner"),
            BacklogItem("seed_session", "Seed or reuse review session", "done", "rulebook_owner", seed_action),
            BacklogItem("run_review", "Execute read-only review surface", "done", "rulebook_owner"),
            BacklogItem("finalize", "Persist final review output", "done", "rulebook_owner"),
        ],
    )
    owner_store.write_findings(
        run_id,
        [
            IntermediateFinding(
                finding_id=f"{agent_id}-review",
                author_agent_id=agent_id,
                summary=f"Read-only review surface '{review_surface}' completed.",
                evidence=(str(session_path),),
            )
        ],
        step_id=f"{agent_id}-review",
    )
    review_sequence = owner_store.next_review_sequence(run_id, review_surface)
    review_path = owner_store.append_review_artifact(
        ReviewArtifactRecord(
            run_id=run_id,
            review_name=review_surface,
            sequence=review_sequence,
            step_id=f"{agent_id}-review",
            spec_version=1,
            owner_run_id=run_id,
            requested_delegate_id=agent_id,
            reviewer_agent_id="rulebook_owner",
            object_id=args.object_id,
            gate_applied=False,
            gate_passed=True,
            payload=asdict(review),
            rationale=("read-only demo surface",),
        )
    )
    owner_store.write_verification(
        run_id,
        [
            VerificationItem(
                "session_unchanged",
                "session bytes are identical before and after review",
                "passed" if before == after else "failed",
                (str(session_path), str(review_path)),
            )
        ],
        step_id=f"{agent_id}-review",
    )
    owner_store.write_final_output(
        FinalOutputRecord(
            run_id=run_id,
            owner_agent_id="rulebook_owner",
            selected_delegate_id=agent_id,
            status="completed",
            summary=f"Owner recorded a read-only review surface result for '{agent_id}'.",
            output_paths=(str(session_path), str(review_path)),
            step_id=f"{agent_id}-review",
        )
    )
    return {
        "agent_id": agent_id,
        "artifacts_root": str(artifacts_root),
        "object_id": args.object_id,
        "review": asdict(review),
        "review_surface": review_surface,
        "seed_action": seed_action,
        "session_mutated": before != after,
        "session_path": str(session_path),
        "status": str(agent_definition["status"]),
    }


def _review_surface_definitions() -> list[dict[str, object]]:
    definitions: list[dict[str, object]] = []
    for export_name in getattr(agent_definitions_module, "__all__", ()):
        candidate = getattr(agent_definitions_module, export_name, None)
        if not isinstance(candidate, dict):
            continue
        review_surface = candidate.get("operator_review_surface")
        if not isinstance(review_surface, dict):
            continue
        if str(review_surface.get("surface_type", "")).strip() != "readonly_review":
            continue
        definitions.append(candidate)
    return sorted(definitions, key=lambda item: str(item.get("agent_id", "")).strip())


def _load_callable(entrypoint: str):
    module_name, _, attribute_name = entrypoint.rpartition(".")
    module = import_module(module_name)
    return getattr(module, attribute_name)


def _review_surface_name(tool_entrypoint: str) -> str:
    function_name = tool_entrypoint.rsplit(".", 1)[-1]
    return function_name.removeprefix("inspect_")


def _seed_review_session(
    *,
    artifacts_root: Path,
    object_id: str,
    subject: str,
    scope: str,
) -> None:
    store = FileObjectStore(Path(artifacts_root).resolve() / "runtime_sessions")
    research_object = ResearchObject(
        object_id=object_id,
        object_type=ObjectType.ASSET,
        scope=scope,
        time_horizon=TimeHorizon.SHORT,
        processing_state=ProcessingState.ACTIVE_RESEARCH,
        risk_state=RiskState.CAUTION,
        attention_score=72,
    )
    claims = [
        _build_claim(
            claim_id=f"{object_id}:c1",
            object_id=object_id,
            subject=subject,
            predicate="spot_breakout",
            value=f"{subject} spot breakout remains constructive",
            claim_type=ClaimType.MEASUREMENT,
            direction=Direction.BULLISH,
            source_family=SourceFamily.CEX,
            evidence_level=EvidenceLevel.E4,
            confidence=82,
            scope=scope,
        ),
        _build_claim(
            claim_id=f"{object_id}:c2",
            object_id=object_id,
            subject=subject,
            predicate="wallet_buy",
            value=f"{subject} onchain buying remains supportive",
            claim_type=ClaimType.FLOW,
            direction=Direction.BULLISH,
            source_family=SourceFamily.ONCHAIN,
            evidence_level=EvidenceLevel.E4,
            confidence=78,
            scope=scope,
        ),
        _build_claim(
            claim_id=f"{object_id}:c3",
            object_id=object_id,
            subject=subject,
            predicate="headline_risk",
            value=f"{subject} still carries headline risk that should remain visible",
            claim_type=ClaimType.RISK_FLAG,
            direction=Direction.RISK,
            source_family=SourceFamily.SAFETY,
            evidence_level=EvidenceLevel.E3,
            confidence=57,
            scope=scope,
        ),
    ]
    research_object.claim_ids = [claim.claim_id for claim in claims]
    store.save(
        RuntimeSession(
            object_id=object_id,
            research_object=research_object,
            claims=claims,
        )
    )


def _build_claim(
    *,
    claim_id: str,
    object_id: str,
    subject: str,
    predicate: str,
    value: str,
    claim_type: ClaimType,
    direction: Direction,
    source_family: SourceFamily,
    evidence_level: EvidenceLevel,
    confidence: int,
    scope: str,
) -> Claim:
    return Claim(
        claim_id=claim_id,
        object_id=object_id,
        claim_type=claim_type,
        subject=subject,
        predicate=predicate,
        value=value,
        direction=direction,
        scope=scope,
        time_horizon=TimeHorizon.SHORT,
        source_family=source_family,
        confidence=confidence,
        status=ClaimStatus.SUPPORTED,
        evidence=[
            EvidenceRef(
                evidence_id=f"{claim_id}:e1",
                level=evidence_level,
                source_family=source_family,
                fresh=True,
            )
        ],
    )


def _error_payload(exc: Exception) -> dict[str, object]:
    return {
        "error": str(exc),
        "error_type": type(exc).__name__,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help(sys.stderr)
        return 2
    try:
        payload = args.func(args)
    except Exception as exc:  # noqa: BLE001 - public demo should emit the exact failure class
        print(json.dumps(_error_payload(exc), indent=2, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
