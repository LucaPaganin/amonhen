"""Exact maximum-weight matching: optimum, determinism, no shared nodes."""
import random

from amonhen.matching import max_weight_matching


def _total(weights, matching):
    return sum(weights[pair] for pair in matching)


def _brute_force(weights):
    """Best total weight by enumerating every matching of the left side."""
    left = sorted({left_id for left_id, _ in weights})
    right_of = {}
    for (left_id, right_id), weight in weights.items():
        right_of.setdefault(left_id, []).append((right_id, weight))
    best = [0]

    def walk(index, used_right, total):
        if index == len(left):
            best[0] = max(best[0], total)
            return
        left_id = left[index]
        walk(index + 1, used_right, total)  # skip this node
        for right_id, weight in right_of.get(left_id, []):
            if right_id in used_right:
                continue
            walk(index + 1, used_right | {right_id}, total + weight)

    walk(0, frozenset(), 0)
    return best[0]


def test_greedy_closest_pair_loses_to_the_optimum():
    # Left 1 is closest to right 1, but taking it strands left 2; the optimum
    # gives right 1 to left 2 and pairs left 1 with right 2. Greedy-by-date
    # (as in phase 1) totals 40, the exact match totals 80.
    weights = {(1, 1): 40, (1, 2): 30, (2, 1): 50}

    matching = max_weight_matching(weights)

    assert matching == [(1, 2), (2, 1)]
    assert _total(weights, matching) == 80


def test_matches_brute_force_on_random_small_instances():
    rng = random.Random(20260912)
    for _ in range(30):
        left_count = rng.randint(1, 6)
        right_count = rng.randint(1, 6)
        weights = {}
        for left_id in range(1, left_count + 1):
            for right_id in range(1, right_count + 1):
                if rng.random() < 0.5:
                    weights[(left_id, right_id)] = rng.randint(1, 100)

        matching = max_weight_matching(weights)

        left_ids = [left for left, _ in matching]
        right_ids = [right for _, right in matching]
        assert len(set(left_ids)) == len(left_ids)
        assert len(set(right_ids)) == len(right_ids)
        assert all(pair in weights for pair in matching)
        assert _total(weights, matching) == _brute_force(weights)


def test_every_node_is_used_at_most_once_with_identical_amounts():
    weights = {
        (debit, credit): 50
        for debit in range(1, 5)
        for credit in range(101, 105)
    }

    matching = max_weight_matching(weights)

    ids = [node for pair in matching for node in pair]
    assert len(ids) == 8
    assert len(set(ids)) == 8
    assert len(matching) == 4
    assert all(pair in weights for pair in matching)


def test_result_is_stable_regardless_of_input_order():
    weights = {(1, 1): 40, (1, 2): 30, (2, 1): 50, (2, 2): 30}
    reversed_weights = dict(reversed(list(weights.items())))

    assert max_weight_matching(weights) == max_weight_matching(reversed_weights)


def test_empty_graph_has_no_matching():
    assert max_weight_matching({}) == []
