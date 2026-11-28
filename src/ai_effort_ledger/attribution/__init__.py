"""The attribution of the events to their dimensions: the matching of the identity rules
and of the category rules, the names of the projects, the buckets of the events, and
the split rule with the figures of the buckets, the project figures, and the parts of
each session, which resolve the project and the work item of an event at report time
(configuration.md › Matching, metrics.md › Attribution, architecture.md › Modules)."""

from .annotations import Bucket, event_buckets
from .names import declared_project_unknown, default_name, project_names
from .rules import (
    category_of,
    effective_category,
    folder_matches,
    more_specific,
    pattern_narrower,
    project_of,
)
from .split import Attribution, BucketFigures, attribute, split_human

__all__ = [
    "Attribution",
    "Bucket",
    "BucketFigures",
    "attribute",
    "category_of",
    "declared_project_unknown",
    "default_name",
    "effective_category",
    "event_buckets",
    "folder_matches",
    "more_specific",
    "pattern_narrower",
    "project_names",
    "project_of",
    "split_human",
]
