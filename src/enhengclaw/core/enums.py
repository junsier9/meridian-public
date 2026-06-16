from __future__ import annotations

from enum import Enum


class StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ObjectType(StringEnum):
    ASSET = "asset"
    NARRATIVE = "narrative"
    EVENT = "event"
    WALLET_CLUSTER = "wallet_cluster"
    PROJECT = "project"
    VENUE = "venue"


class ProcessingState(StringEnum):
    CANDIDATE = "candidate"
    SCREENED = "screened"
    ACTIVE_RESEARCH = "active_research"
    EVIDENCE_COMPLETE = "evidence_complete"
    PUBLISH_READY = "publish_ready"
    PUBLISHED = "published"
    MONITORING = "monitoring"
    ARCHIVED = "archived"
    BLOCKED = "blocked"


class RiskState(StringEnum):
    NORMAL = "normal"
    CAUTION = "caution"
    RESTRICTED = "restricted"
    BLOCKED = "blocked"


class MarketState(StringEnum):
    PRE_EMERGENCE = "pre_emergence"
    EMERGING = "emerging"
    ACCELERATING = "accelerating"
    CROWDED = "crowded"
    DISTRIBUTION = "distribution"
    FADING = "fading"
    INVALIDATED = "invalidated"


class ClaimType(StringEnum):
    FACT = "fact"
    MEASUREMENT = "measurement"
    FLOW = "flow"
    MARKET_STRUCTURE = "market_structure"
    CAUSAL = "causal"
    PREDICTIVE = "predictive"
    RISK_FLAG = "risk_flag"
    INVALIDATION = "invalidation"


class ClaimStatus(StringEnum):
    PROPOSED = "proposed"
    GROUNDED = "grounded"
    SUPPORTED = "supported"
    CONTESTED = "contested"
    PROMOTED = "promoted"
    STALE = "stale"
    INVALIDATED = "invalidated"
    ARCHIVED = "archived"


class ThesisType(StringEnum):
    DESCRIPTIVE = "descriptive"
    CAUSAL = "causal"
    PREDICTIVE = "predictive"
    RISK = "risk"
    COUNTER = "counter"


class ThesisStatus(StringEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    CHALLENGED = "challenged"
    PUBLISHABLE = "publishable"
    PUBLISHED = "published"
    MONITORING = "monitoring"
    INVALIDATED = "invalidated"
    ARCHIVED = "archived"


class Direction(StringEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    RISK = "risk"
    INVALIDATING = "invalidating"


class EvidenceLevel(StringEnum):
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"
    E5 = "E5"

    @property
    def rank(self) -> int:
        return {
            EvidenceLevel.E1: 1,
            EvidenceLevel.E2: 2,
            EvidenceLevel.E3: 3,
            EvidenceLevel.E4: 4,
            EvidenceLevel.E5: 5,
        }[self]


class SourceFamily(StringEnum):
    INFOFLOW = "infoflow"
    CEX = "cex"
    ONCHAIN = "onchain"
    ANALYTICS = "analytics"
    SAFETY = "safety"
    OFFICIAL = "official"


class TimeHorizon(StringEnum):
    INTRADAY = "intraday"
    SHORT = "short"
    MEDIUM = "medium"
    STRUCTURAL = "structural"


class ConflictSeverity(StringEnum):
    CLEAN = "clean"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {
            ConflictSeverity.CLEAN: 0,
            ConflictSeverity.LOW: 1,
            ConflictSeverity.MEDIUM: 2,
            ConflictSeverity.HIGH: 3,
            ConflictSeverity.CRITICAL: 4,
        }[self]


class ConflictResolution(StringEnum):
    CLEAN = "clean"
    RESOLVED = "resolved"
    SCOPE_SPLIT = "scope_split"
    TIME_SPLIT = "time_split"
    UNRESOLVED = "unresolved"


class ResourceTier(StringEnum):
    A = "tier_a"
    B = "tier_b"
    C = "tier_c"
    D = "tier_d"
    E = "tier_e"


class SlotType(StringEnum):
    DEEP = "deep"
    CONFLICT = "conflict"
    PUBLISH = "publish"
    MONITORING = "monitoring"
    NONE = "none"
