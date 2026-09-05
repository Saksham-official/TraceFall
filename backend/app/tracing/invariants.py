"""The accounting invariant.

Every unit of the victim's value must end up in exactly one of three places: attributed
onward along a recorded edge, recorded as pruned, or retained at an address. Value is
never created.

This is asserted after every trace, in production and not only in tests — it is the
single best check that the engine is correct, and a violation means a number in a police
report is wrong.
"""

from fractions import Fraction

from app.tracing.models import TraceResult


class AccountingError(AssertionError):
    """The trace attributed more value than entered it, or lost some."""


def check(result: TraceResult) -> None:
    for node in result.nodes.values():
        if node.retained < 0:
            raise AccountingError(
                f"{node.address} attributed {node.attributed_out} and pruned "
                f"{node.pruned_out} out of {node.tainted_in} received — taint was created"
            )

    accounted: Fraction = result.total_retained + result.total_pruned
    if accounted != result.original_amount:
        raise AccountingError(
            f"trace from {result.root} accounts for {accounted} of "
            f"{result.original_amount} (difference {result.original_amount - accounted})"
        )
