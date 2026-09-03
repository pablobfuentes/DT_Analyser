"""Pre-entry protection for cohort filters and analysis dimensions."""

from __future__ import annotations

from app.services.research.variables import FILTER_TIMING, PRE_ENTRY_CLASSES, heatmap_dim, variable_by_key


class LookaheadFilterError(ValueError):
    def __init__(self, keys: list[str]):
        self.keys = keys
        super().__init__(
            "Not available before trade entry: " + ", ".join(keys)
        )


class RetrospectiveRuleError(ValueError):
    """Retrospective filters may be saved, but cannot enter FORWARD_TESTING."""

    code = "RETROSPECTIVE_RULE_NOT_FORWARD_TESTABLE"

    def __init__(self, keys: list[str]):
        self.keys = keys
        super().__init__(
            "This pattern uses information unavailable by entry and cannot be "
            "forward-tested as an entry rule."
        )


def filter_timing(exploration_key: str) -> str:
    return FILTER_TIMING.get(exploration_key, "EXIT")


def is_pre_entry_filter(exploration_key: str) -> bool:
    return filter_timing(exploration_key) in PRE_ENTRY_CLASSES


def validate_cohort_filters(filters: dict[str, str], research_mode: str) -> list[str]:
    """Return rejected keys. Raises LookaheadFilterError in PRE_ENTRY_ONLY."""
    rejected = [k for k in filters if k and not is_pre_entry_filter(k)]
    if research_mode == "PRE_ENTRY_ONLY" and rejected:
        raise LookaheadFilterError(rejected)
    return rejected


def cohort_is_retrospective(filters: dict[str, str]) -> bool:
    return any(not is_pre_entry_filter(k) for k in filters)


def validate_variable_mode(var_key: str, research_mode: str, role: str = "axis") -> None:
    spec = variable_by_key(var_key)
    if spec is None:
        raise ValueError(f"Unknown research variable: {var_key}")
    if research_mode == "PRE_ENTRY_ONLY" and spec["timing_class"] not in PRE_ENTRY_CLASSES:
        raise LookaheadFilterError([var_key])


def retrospective_filter_keys(filters: dict[str, str]) -> list[str]:
    return [k for k in filters if k and not is_pre_entry_filter(k)]


def assert_forward_testable(filters: dict[str, str], status: str) -> None:
    if str(status or "").upper() != "FORWARD_TESTING":
        return
    bad = retrospective_filter_keys(filters)
    if bad:
        raise RetrospectiveRuleError(bad)


def validate_heatmap_dim(dim_key: str, research_mode: str) -> dict:
    spec = heatmap_dim(dim_key)
    if spec is None:
        raise ValueError(f"Unknown heatmap dimension: {dim_key}")
    if research_mode == "PRE_ENTRY_ONLY" and spec["timing_class"] not in PRE_ENTRY_CLASSES:
        raise LookaheadFilterError([dim_key])
    return spec
