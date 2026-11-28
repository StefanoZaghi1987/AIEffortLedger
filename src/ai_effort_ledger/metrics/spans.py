"""The algebra of spans: the union, the intersection, the difference, the total length of sets
of half-open intervals of milliseconds, and the sum of such totals over keys.

A span is `(start, end)`, milliseconds since the epoch, with the start instant included and
the end instant excluded (decision D12: the figures are computed in milliseconds). Every
function treats its argument as a set of instants: the spans may overlap, touch, and arrive
in any order, and empty spans contribute nothing. Each list is the sorted, disjoint spans
that the operation gives.
"""

from collections.abc import Hashable, Iterable

Span = tuple[int, int]
"""A half-open interval of milliseconds since the epoch: the start included, the end excluded."""


def union(spans: Iterable[Span]) -> list[Span]:
    """The instants of the spans as sorted, disjoint spans: overlapping and touching spans
    merge, and empty spans disappear."""
    merged: list[Span] = []
    for start, end in sorted(spans):
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def intersect(a: Iterable[Span], b: Iterable[Span]) -> list[Span]:
    """The instants that the two sets of spans share."""
    left, right = union(a), union(b)
    shared: list[Span] = []
    index = 0
    for start, end in left:
        while index < len(right) and right[index][1] <= start:
            index += 1
        while index < len(right):
            other_start, other_end = right[index]
            if other_start >= end:
                break
            shared.append((max(start, other_start), min(end, other_end)))
            if other_end < end:
                index += 1
            else:
                break
    return shared


def subtract(a: Iterable[Span], b: Iterable[Span]) -> list[Span]:
    """The instants of the spans of `a` that no span of `b` covers."""
    left, right = union(a), union(b)
    remaining: list[Span] = []
    index = 0
    for start, end in left:
        cursor = start
        while index < len(right) and right[index][1] <= cursor:
            index += 1
        while index < len(right) and right[index][0] < end:
            other_start, other_end = right[index]
            if other_start > cursor:
                remaining.append((cursor, other_start))
            cursor = max(cursor, other_end)
            if cursor >= end:
                break
            index += 1
        if cursor < end:
            remaining.append((cursor, end))
    return remaining


def total(spans: Iterable[Span]) -> int:
    """The length of the union of the spans, in milliseconds: an instant counts once."""
    return sum(end - start for start, end in union(spans))


def total_by_key(keyed: Iterable[tuple[Span, Hashable]]) -> int:
    """The sum over the keys of `total` of the spans of each key, in milliseconds: an
    instant counts once for each key. It measures the agent time of a holder, each span
    with the agent that works it: the agent time of a set of agents is the sum over the
    agents, and the parts of one agent that overlap or touch count once (metrics.md › Agent
    time)."""
    grouped: dict[Hashable, list[Span]] = {}
    for span, key in keyed:
        grouped.setdefault(key, []).append(span)
    return sum(total(spans) for spans in grouped.values())
