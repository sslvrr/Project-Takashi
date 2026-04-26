"""
Capital scaling — controls how much of the calculated position size
to actually deploy based on current equity tier.
Prevents over-exposure during early stages or after drawdowns.
"""


def capital_scale(equity: float) -> float:
    """
    Return a multiplier [0, 1] applied to the raw position size.
    Tier structure from the sprint plan:
      <$10k  → 10% deployment (micro)
      <$50k  → 30% deployment (growing)
      ≥$50k  → 50% deployment (scaled)
    """
    if equity < 10_000:
        return 0.10
    elif equity < 50_000:
        return 0.30
    else:
        return 0.50


def scale_position(raw_size: float, equity: float) -> float:
    """Apply capital scaling to a raw position size."""
    return raw_size * capital_scale(equity)
