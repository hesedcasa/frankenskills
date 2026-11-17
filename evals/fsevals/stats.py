"""Means, bootstrap confidence intervals, and paired arm differences."""

from __future__ import annotations

import random
from statistics import mean


def _clean(xs):
    return [float(x) for x in xs if x is not None]


def bootstrap_ci(xs, iters: int = 2000, alpha: float = 0.05, seed: int = 0):
    xs = _clean(xs)
    if not xs:
        return None, None, None
    if len(xs) == 1:
        return xs[0], None, None
    rng = random.Random(seed)
    means = sorted(mean(rng.choices(xs, k=len(xs))) for _ in range(iters))
    lo = means[int(alpha / 2 * iters)]
    hi = means[int((1 - alpha / 2) * iters) - 1]
    return mean(xs), lo, hi


def paired_diff(a: dict, b: dict, **kw):
    """Mean of b[k] - a[k] over keys present in both, with a bootstrap CI."""
    keys = [k for k in a if k in b and a[k] is not None and b[k] is not None]
    diffs = [float(b[k]) - float(a[k]) for k in keys]
    m, lo, hi = bootstrap_ci(diffs, **kw)
    return {"n": len(diffs), "mean": m, "lo": lo, "hi": hi}


def fmt(m, lo=None, hi=None, pct: bool = False) -> str:
    if m is None:
        return "—"
    f = (lambda v: f"{100 * v:.1f}%") if pct else (lambda v: f"{v:.3g}")
    return f(m) if lo is None else f"{f(m)} [{f(lo)}, {f(hi)}]"
