"""Data models for the Conversation Analysis System."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Conversation:
    id: str                  # MongoDB _id
    widget_id: str           # Brand identifier
    created_at: datetime
    updated_at: datetime


@dataclass
class Message:
    id: str
    conversation_id: str
    sender: str              # "user" | "agent"
    message_type: str        # "text" | "event"
    text: str
    timestamp: datetime
    metadata: dict = field(default_factory=dict)  # event metadata, e.g. eventType


@dataclass
class EnrichedConversation:
    conversation: Conversation
    messages: list[Message]  # sorted by timestamp ascending


@dataclass
class FlaggedResponse:
    message_id: str
    flag_type: str           # "irrelevant" | "hallucination" | "verbose"
    confidence: float        # 0.0 – 1.0
    reason: str


@dataclass
class AnalysisResult:
    conversation_id: str
    widget_id: str
    topic_categories: list[str]
    is_drop_off: bool
    is_unanswered: bool
    frustration_score: float          # 0.0 – 1.0
    flagged_responses: list[FlaggedResponse]
    product_engagement: bool
    low_engagement_product_rec: bool


@dataclass
class BrandMetrics:
    widget_id: str
    total_conversations: int
    drop_off_rate: float
    frustration_rate: float
    response_quality_score: float
    product_engagement_rate: float
    outlier_flags: list[str] = field(default_factory=list)


@dataclass
class ReportSummary:
    total_conversations: int
    total_brands: int
    overall_drop_off_rate: float
    top_3_issues: list[str]


@dataclass
class FlaggedConversation:
    conversation_id: str
    widget_id: str
    flag_reason: str
    drop_off: bool
    frustration_score: float
    flagged_responses: list[FlaggedResponse]


@dataclass
class ConversationPattern:
    pattern_name: str
    description: str
    evidence: str          # what data supports this pattern
    affected_brands: list[str] = field(default_factory=list)
    conversation_count: int = 0


@dataclass
class Insight:
    title: str
    description: str
    severity: str        # "HIGH" | "MEDIUM" | "LOW"
    recommendation: str
    affected_brands: list[str] = field(default_factory=list)


@dataclass
class AggregatedReport:
    run_date: datetime
    filters_applied: dict
    brand_metrics: list[BrandMetrics]
    flagged_conversations: list[FlaggedConversation]
    systemic_issues: list[str]
    brand_specific_issues: dict[str, list[str]]
    summary: ReportSummary
    insights: list[Insight] = field(default_factory=list)
    patterns: list[ConversationPattern] = field(default_factory=list)


@dataclass
class RunRecord:
    run_date: datetime
    brand_metrics: list[BrandMetrics]
