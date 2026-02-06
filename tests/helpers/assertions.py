from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import isnan
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class MissingRateResult:
    field: str
    missing: int
    total: int

    @property
    def rate(self) -> float:
        return self.missing / max(self.total, 1)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def assert_required_fields(obj: Any, fields: Sequence[str], *, context: str = "") -> None:
    missing = []
    nulls = []

    if isinstance(obj, Mapping):
        for f in fields:
            if f not in obj:
                missing.append(f)
            elif _is_missing(obj.get(f)):
                nulls.append(f)
    else:
        for f in fields:
            if not hasattr(obj, f):
                missing.append(f)
            elif _is_missing(getattr(obj, f)):
                nulls.append(f)

    if missing or nulls:
        msg = ["Required fields check failed"]
        if context:
            msg.append(f"context={context}")
        if missing:
            msg.append(f"missing_fields={missing}")
        if nulls:
            msg.append(f"null_or_empty_fields={nulls}")
        raise AssertionError(" | ".join(msg))


def assert_missing_rate(
    items: Sequence[Any],
    field: str,
    max_rate: float,
    *,
    context: str = "",
    sample: int = 5,
) -> MissingRateResult:
    values = []
    for item in items:
        if isinstance(item, Mapping):
            values.append(item.get(field))
        else:
            values.append(getattr(item, field, None))

    total = len(values)
    missing_idx = [i for i, v in enumerate(values) if _is_missing(v)]
    missing = len(missing_idx)
    result = MissingRateResult(field=field, missing=missing, total=total)

    if result.rate > max_rate:
        examples = [values[i] for i in missing_idx[:sample]]
        msg = ["Missingness threshold exceeded"]
        if context:
            msg.append(f"context={context}")
        msg.append(f"field={field}")
        msg.append(f"missing={missing}/{total} rate={result.rate:.3f} max_rate={max_rate:.3f}")
        msg.append(f"sample_missing_values={examples}")
        raise AssertionError(" | ".join(msg))

    return result


def assert_in_range(
    values: Iterable[Any],
    *,
    min: float | None = None,
    max: float | None = None,
    allow_nan: bool = False,
    allow_none: bool = False,
    context: str = "",
    sample: int = 5,
    # Backwards-compatible kw names.
    min_value: float | None = None,
    max_value: float | None = None,
) -> None:
    if min is None:
        min = min_value
    if max is None:
        max = max_value

    bad = []
    observed = []

    for v in values:
        if v is None:
            if allow_none:
                continue
            bad.append(v)
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            bad.append(v)
            continue
        if isnan(fv):
            if allow_nan:
                continue
            bad.append(v)
            continue

        observed.append(fv)
        if min is not None and fv < min:
            bad.append(v)
        elif max is not None and fv > max:
            bad.append(v)

    if bad:
        msg = ["Range check failed"]
        if context:
            msg.append(f"context={context}")
        msg.append(f"min={min} max={max}")
        if observed:
            msg.append(f"observed_min={min(observed):.6g} observed_max={max(observed):.6g}")
        msg.append(f"sample_invalid={bad[:sample]}")
        raise AssertionError(" | ".join(msg))


def assert_allowed_values(
    values: Iterable[Any],
    allowed: set[Any],
    *,
    context: str = "",
    sample: int = 10,
) -> None:
    unexpected = [v for v in values if v not in allowed]
    if unexpected:
        counts = Counter(unexpected)
        top = counts.most_common(sample)
        msg = ["Allowed-values check failed"]
        if context:
            msg.append(f"context={context}")
        msg.append(f"allowed_count={len(allowed)}")
        msg.append(f"unexpected_count={len(unexpected)}")
        msg.append(f"unexpected_top={top}")
        raise AssertionError(" | ".join(msg))


def assert_unique(values: Iterable[Any], *, context: str = "", sample: int = 10) -> None:
    vals = list(values)
    counts = Counter(vals)
    dups = [v for v, c in counts.items() if c > 1]
    if dups:
        msg = ["Uniqueness check failed"]
        if context:
            msg.append(f"context={context}")
        msg.append(f"duplicates_count={len(dups)}")
        msg.append(f"sample_duplicates={dups[:sample]}")
        raise AssertionError(" | ".join(msg))


def assert_probability_vector(vec: Sequence[float], *, tol: float = 1e-6, context: str = "") -> None:
    if vec is None:
        raise AssertionError(f"Probability vector is None | context={context}")
    if len(vec) == 0:
        raise AssertionError(f"Probability vector is empty | context={context}")

    total = 0.0
    bad = []
    for v in vec:
        try:
            fv = float(v)
        except (TypeError, ValueError):
            bad.append(v)
            continue
        if fv < -tol or fv > 1.0 + tol:
            bad.append(v)
        total += fv

    if bad:
        raise AssertionError(f"Probability vector values out of [0,1] | context={context} | sample_invalid={bad[:10]}")

    if abs(total - 1.0) > tol:
        raise AssertionError(f"Probability vector does not sum to 1 | context={context} | sum={total} tol={tol}")
