"""The metrics engine: the spans, the measured human time, the turns with their parts of
agent time and the blocked time of the agents, and the manual entries with the activity
classes of the person (architecture.md › Modules)."""

from .agent import Agent, AgentPart, BlockedInterval, Turn, agent_parts, blocked_intervals, turns
from .classes import ManualPart, Metrics, activity_classes, compute_metrics, manual_parts
from .human import (
    HumanInterval,
    MetricsParameters,
    Stream,
    human_intervals,
    human_signals,
    human_time_at_idle_gaps,
    instant_ms,
    presence_span,
    stored_category,
    stream_of,
    unknown_invocation_share,
)
from .spans import Span, intersect, subtract, total, total_by_key, union

__all__ = [
    "Agent",
    "AgentPart",
    "BlockedInterval",
    "HumanInterval",
    "ManualPart",
    "Metrics",
    "MetricsParameters",
    "Span",
    "Stream",
    "Turn",
    "activity_classes",
    "agent_parts",
    "blocked_intervals",
    "compute_metrics",
    "human_intervals",
    "human_signals",
    "human_time_at_idle_gaps",
    "instant_ms",
    "intersect",
    "manual_parts",
    "presence_span",
    "stored_category",
    "stream_of",
    "subtract",
    "total",
    "total_by_key",
    "turns",
    "union",
    "unknown_invocation_share",
]
