"""Proportional (haircut) taint attribution — ADR-004.

On an account-model chain, balances are pooled and fungible. When a wallet holding
50,000 USDT receives 40,000 from a victim and later sends 60,000 onward, there is no
fact of the matter about how much of the victim's money moved. Any answer is a
convention someone chose.

Ours is proportional: if 40% of everything that flowed into an address was traced from
the victim, then 40% of everything that leaves it is attributed to the victim. It is
symmetric, order-independent, conservative, and explains in one sentence to a
non-technical reader — which matters more here than sophistication, because an
investigator may have to defend it.
"""

from fractions import Fraction

from app.normalize.transfer import NormalizedTransfer

TAINT_MODEL_NOTE = (
    "Proportional (haircut) attribution. Amounts shown are attributed value, not "
    "identifiable coins."
)


def inbound_total(transfers: list[NormalizedTransfer], address: str) -> int:
    """Everything that flowed in — tainted and untainted alike. The haircut denominator."""
    return sum(t.amount_raw for t in transfers if t.to_address == address and t.succeeded)


def haircut_ratio(tainted_in: Fraction, total_in: int, total_out: int) -> Fraction:
    """The fraction of value leaving this address that is attributed to the victim.

    The denominator is `max(total_in, total_out)`, not `total_in` alone. An address can
    send out more than the inflow we observe — it may have held a balance before the
    victim paid, or the earlier history may fall outside the analysis window. Dividing by
    inflow alone would then attribute more tainted value than ever arrived, which lets the
    trace create money out of nothing.

    Using the larger of the two makes the total attributed onward at most `tainted_in` in
    every case, and reduces to the textbook haircut whenever outflow does not exceed
    inflow. Whatever is not attributed onward is retained at the address — either still
    sitting there, or diluted away by untainted funds.
    """
    denominator = max(total_in, total_out)
    if denominator <= 0:
        return Fraction(0)
    return min(tainted_in / Fraction(denominator), Fraction(1))


def attribute(amount_raw: int, ratio: Fraction) -> Fraction:
    """The tainted share of one outgoing flow."""
    return Fraction(amount_raw) * ratio
