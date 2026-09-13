"""Exact maximum-weight bipartite matching for transfer reconciliation.

Desiderata 5.3 asks the ambiguous cases to be resolved by a maximum-weight
bipartite matching rather than a greedy closest-date pick. The graphs are small
(legs sharing an amount inside a two-day window) but the distinction matters: a
pair that is locally best can block a pairing with a larger total weight.

Algorithm: the Kuhn-Munkres (Hungarian) assignment on the cost matrix
``-weight``, with absent edges carrying cost ``0`` so they are only ever chosen
when no positive-weight edge remains. The rows are the smaller side of the
graph. Complexity is O(n^2 m) time and O(n m) space for ``n = min(|L|, |R|)``
rows and ``m = max(|L|, |R|)`` columns, i.e. O(V^3) on a balanced graph.

Ids are processed in ascending order and ties resolve to the smallest id, so
the result is deterministic.

Precondition: the left and right id spaces are disjoint (the callers split the
candidate legs by amount sign). The algorithm partitions ids into two
independent sides and does not check for overlap, so an id present on both
sides would be matched twice.
"""
from __future__ import annotations

from typing import Mapping

_INFINITY = float("inf")


def max_weight_matching(weights: Mapping[tuple[int, int], int]) -> list[tuple[int, int]]:
    """Return a maximum-total-weight matching of the bipartite graph.

    ``weights`` maps ``(left_id, right_id)`` to a positive integer weight;
    keys that are absent are non-edges. Every id appears at most once in the
    result, which is sorted and contains only pairs present in ``weights``.
    """
    edges = {pair: weight for pair, weight in weights.items() if weight > 0}
    if not edges:
        return []

    left = sorted({left_id for left_id, _ in edges})
    right = sorted({right_id for _, right_id in edges})
    if len(left) <= len(right):
        rows, columns, transposed = left, right, False
    else:
        rows, columns, transposed = right, left, True

    # Minimising -weight maximises the total; a missing edge costs 0, so it can
    # never displace an edge that carries evidence.
    cost = [
        [
            -edges.get((row, column) if not transposed else (column, row), 0)
            for column in columns
        ]
        for row in rows
    ]

    matching: list[tuple[int, int]] = []
    for row_index, column_index in _hungarian(cost):
        left_id = rows[row_index]
        right_id = columns[column_index]
        pair = (left_id, right_id) if not transposed else (right_id, left_id)
        if pair in edges:
            matching.append(pair)
    matching.sort()
    return matching


def _hungarian(cost: list[list[int]]) -> list[tuple[int, int]]:
    """Minimum-cost assignment of every row, rows <= columns.

    Standard Kuhn-Munkres with potentials; the scan order makes ties settle on
    the smallest column index. Returns ``(row_index, column_index)`` pairs.
    """
    row_count = len(cost)
    if row_count == 0:
        return []
    column_count = len(cost[0])

    row_potential = [0] * (row_count + 1)
    column_potential = [0] * (column_count + 1)
    assigned_row = [0] * (column_count + 1)
    previous = [0] * (column_count + 1)

    for row in range(1, row_count + 1):
        assigned_row[0] = row
        column = 0
        min_slack = [_INFINITY] * (column_count + 1)
        used = [False] * (column_count + 1)
        while True:
            used[column] = True
            current_row = assigned_row[column]
            delta = _INFINITY
            next_column = 0
            for candidate in range(1, column_count + 1):
                if used[candidate]:
                    continue
                slack = (
                    cost[current_row - 1][candidate - 1]
                    - row_potential[current_row]
                    - column_potential[candidate]
                )
                if slack < min_slack[candidate]:
                    min_slack[candidate] = slack
                    previous[candidate] = column
                if min_slack[candidate] < delta:
                    delta = min_slack[candidate]
                    next_column = candidate
            for candidate in range(column_count + 1):
                if used[candidate]:
                    row_potential[assigned_row[candidate]] += delta
                    column_potential[candidate] -= delta
                else:
                    min_slack[candidate] -= delta
            column = next_column
            if assigned_row[column] == 0:
                break
        while column:
            previous_column = previous[column]
            assigned_row[column] = assigned_row[previous_column]
            column = previous_column

    return [
        (assigned_row[column] - 1, column - 1)
        for column in range(1, column_count + 1)
        if assigned_row[column] != 0
    ]
