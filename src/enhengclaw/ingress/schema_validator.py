from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from enhengclaw.core.enums import ClaimType, Direction, EvidenceLevel, ObjectType, SourceFamily, TimeHorizon
from enhengclaw.domain.identity.subject_key import SubjectKey, ensure_subject_symbol_matches


class SchemaValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AgentIngressContext:
    object_id: str
    object_type: ObjectType
    subject: str
    scope: str
    scenario: str
    venue: str = "agent_ingress"
    instrument_type: str = "agent_output"

    @property
    def subject_key(self) -> SubjectKey:
        return SubjectKey.build(
            symbol=self.subject,
            venue=self.venue,
            instrument_type=self.instrument_type,
        )


@dataclass(frozen=True, slots=True)
class ValidatedAgentSignal:
    input_id: str
    subject: str
    predicate: str
    value: str
    claim_type: ClaimType
    direction: Direction
    source_family: SourceFamily
    evidence_level: EvidenceLevel
    confidence_hint: int
    scope: str
    time_horizon: TimeHorizon
    subject_key: SubjectKey


class AgentSchemaValidator:
    required_fields = frozenset(
        {
            "input_id",
            "subject",
            "predicate",
            "value",
            "claim_type",
            "direction",
            "source_family",
            "evidence_level",
            "confidence_hint",
            "scope",
            "time_horizon",
        }
    )

    def validate(
        self,
        payload: Mapping[str, Any],
        *,
        context: AgentIngressContext,
    ) -> ValidatedAgentSignal:
        if not isinstance(payload, Mapping):
            raise SchemaValidationError("agent payload must be a JSON object")

        unknown_fields = sorted(set(payload.keys()) - self.required_fields)
        missing_fields = sorted(field for field in self.required_fields if field not in payload)
        if unknown_fields:
            raise SchemaValidationError(f"agent payload contains unknown fields: {', '.join(unknown_fields)}")
        if missing_fields:
            raise SchemaValidationError(f"agent payload is missing required fields: {', '.join(missing_fields)}")

        input_id = self._require_non_empty_string(payload.get("input_id"), field="input_id")
        subject = self._require_non_empty_string(payload.get("subject"), field="subject")
        try:
            ensure_subject_symbol_matches(context.subject, subject, context="AgentSchemaValidator")
        except ValueError as exc:
            raise SchemaValidationError(str(exc)) from exc
        scope = self._require_non_empty_string(payload.get("scope"), field="scope")
        if scope.strip().lower() != context.scope.strip().lower():
            raise SchemaValidationError(
                f"agent payload scope mismatch: expected '{context.scope}', observed '{scope}'"
            )

        confidence_hint = self._parse_confidence_hint(payload.get("confidence_hint"))
        return ValidatedAgentSignal(
            input_id=input_id,
            subject=subject,
            predicate=self._require_non_empty_string(payload.get("predicate"), field="predicate"),
            value=self._require_non_empty_string(payload.get("value"), field="value"),
            claim_type=self._parse_enum(payload.get("claim_type"), ClaimType, field="claim_type"),
            direction=self._parse_enum(payload.get("direction"), Direction, field="direction"),
            source_family=self._parse_enum(payload.get("source_family"), SourceFamily, field="source_family"),
            evidence_level=self._parse_enum(payload.get("evidence_level"), EvidenceLevel, field="evidence_level"),
            confidence_hint=confidence_hint,
            scope=scope,
            time_horizon=self._parse_enum(payload.get("time_horizon"), TimeHorizon, field="time_horizon"),
            subject_key=context.subject_key,
        )

    def _parse_enum(self, value: Any, enum_type: type, *, field: str):
        if not isinstance(value, str) or not value.strip():
            raise SchemaValidationError(f"agent payload field '{field}' must be a non-empty string")
        try:
            return enum_type(value.strip())
        except ValueError as exc:
            allowed = ", ".join(item.value for item in enum_type)
            raise SchemaValidationError(f"agent payload field '{field}' must be one of: {allowed}") from exc

    def _parse_confidence_hint(self, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise SchemaValidationError("agent payload field 'confidence_hint' must be an integer")
        if value < 0 or value > 100:
            raise SchemaValidationError("agent payload field 'confidence_hint' must be between 0 and 100")
        return value

    def _require_non_empty_string(self, value: Any, *, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise SchemaValidationError(f"agent payload field '{field}' must be a non-empty string")
        return value.strip()
