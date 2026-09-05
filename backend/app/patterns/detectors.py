"""The detectors.

Each is an independent function over a `Subject`, with its thresholds declared beside it
and its false positives stated in full. **None of these is evidence of fraud.** Each one
names a *shape*, and every shape here has an innocent explanation that occurs more often
than the guilty one — which is exactly why the note is mandatory and travels with the
finding to the UI and into the report.

Ordered by MVP priority: fan-out, fan-in and rapid transfer are must-haves; peel chain,
dormancy burst and structuring are `SHOULD` and are the fourth thing on the cut list
(MVP_SCOPE.md section 6).
"""

from collections import Counter
from datetime import timedelta
from typing import Any

from app.db.models.enums import PatternType
from app.patterns.base import Finding, Subject, register, severity_from


@register(
    PatternType.FAN_OUT,
    config={"min_recipients": 8, "window_hours": 24},
    false_positive_note=(
        "Exchange, payment-processor and payroll wallets fan out to many recipients by "
        "design, and an airdrop or batch-payment contract produces an identical shape. "
        "Fan-out is only suggestive when the sending address is not itself an identified "
        "service."
    ),
)
def fan_out(subject: Subject, config: dict[str, Any]) -> list[Finding]:
    """One address dispersing to many — the classic first move after a theft."""
    findings = []
    for address in subject.graph.nodes:
        outbound = subject.outbound(address)
        recipients = {t.to_address for t in outbound}
        if len(recipients) < config["min_recipients"]:
            continue
        window = _within_window(outbound, config["window_hours"])
        if len({t.to_address for t in window}) < config["min_recipients"]:
            continue
        findings.append(
            Finding(
                pattern_type=PatternType.FAN_OUT,
                severity=severity_from(len(recipients), medium=15, high=40),
                subject_address=address,
                involved_addresses=sorted(recipients),
                trigger_tx_hashes=[t.tx_hash for t in window],
                metrics={
                    "recipient_count": len(recipients),
                    "transfer_count": len(outbound),
                    "window_hours": config["window_hours"],
                },
                explanation=(
                    f"{address} sent funds to {len(recipients)} different addresses, "
                    f"{len({t.to_address for t in window})} of them within "
                    f"{config['window_hours']} hours. Dispersing funds across many "
                    f"addresses is a common way to complicate tracing."
                ),
            )
        )
    return findings


@register(
    PatternType.FAN_IN,
    config={"min_senders": 8, "window_hours": 24},
    false_positive_note=(
        "This is the normal shape of an exchange deposit address, a merchant payment "
        "address, and a donation address. Consolidation is only suggestive when the "
        "receiving address is not an identified service — and most of the time it is one."
    ),
)
def fan_in(subject: Subject, config: dict[str, Any]) -> list[Finding]:
    """Many addresses consolidating into one — a collection point."""
    findings = []
    for address in subject.graph.nodes:
        inbound = subject.inbound(address)
        senders = {t.from_address for t in inbound}
        if len(senders) < config["min_senders"]:
            continue
        window = _within_window(inbound, config["window_hours"])
        findings.append(
            Finding(
                pattern_type=PatternType.FAN_IN,
                severity=severity_from(len(senders), medium=15, high=40),
                subject_address=address,
                involved_addresses=sorted(senders),
                trigger_tx_hashes=[t.tx_hash for t in window],
                metrics={"sender_count": len(senders), "transfer_count": len(inbound)},
                explanation=(
                    f"{address} received funds from {len(senders)} different addresses. "
                    f"Consolidation points are where an operation's funds gather, and are "
                    f"often the most useful address in a trace."
                ),
            )
        )
    return findings


@register(
    PatternType.RAPID_TRANSFER,
    config={"max_seconds": 3_600, "min_occurrences": 2},
    false_positive_note=(
        "Automated sweepers, exchange internal operations, and trading bots all move "
        "funds within seconds as a matter of routine. Speed on its own is a property of "
        "automation, not of intent."
    ),
)
def rapid_transfer(subject: Subject, config: dict[str, Any]) -> list[Finding]:
    """Value received and moved on almost immediately — no time to be a destination."""
    findings = []
    for address in subject.graph.nodes:
        inbound = subject.inbound(address)
        outbound = subject.outbound(address)
        if not inbound or not outbound:
            continue

        gaps, hashes = [], []
        for sent in outbound:
            preceding = [t for t in inbound if t.block_time <= sent.block_time]
            if not preceding:
                continue
            gap = int((sent.block_time - preceding[-1].block_time).total_seconds())
            if gap <= config["max_seconds"]:
                gaps.append(gap)
                hashes += [preceding[-1].tx_hash, sent.tx_hash]
        if len(gaps) < config["min_occurrences"]:
            continue

        fastest = min(gaps)
        findings.append(
            Finding(
                pattern_type=PatternType.RAPID_TRANSFER,
                # Faster is more notable, so the scale is inverted.
                severity=severity_from(-fastest, medium=-600, high=-60),
                subject_address=address,
                involved_addresses=sorted({t.to_address for t in outbound}),
                trigger_tx_hashes=list(dict.fromkeys(hashes)),
                metrics={
                    "occurrences": len(gaps),
                    "fastest_seconds": fastest,
                    "median_seconds": sorted(gaps)[len(gaps) // 2],
                },
                explanation=(
                    f"{address} forwarded funds {len(gaps)} times within "
                    f"{config['max_seconds'] // 60} minutes of receiving them, the fastest "
                    f"after {fastest} seconds. Funds passing straight through suggest a "
                    f"relay rather than a destination."
                ),
            )
        )
    return findings


@register(
    PatternType.PEEL_CHAIN,
    config={"min_length": 3, "min_carried": 0.8, "max_peel": 0.2},
    false_positive_note=(
        "Ordinary wallet software produces the same shape with change addresses, and any "
        "hop that pays a fee or a small commission peels value the same way. A long chain "
        "of forwarding is not by itself evidence of laundering."
    ),
)
def peel_chain(subject: Subject, config: dict[str, Any]) -> list[Finding]:
    """A chain where each hop forwards most of the value and peels a little off."""
    graph = subject.graph
    findings = []
    visited: set[str] = set()

    for start in sorted(graph.nodes):
        if start in visited:
            continue
        chain, hashes, peeled = [start], [], 0
        cursor = start
        while True:
            successors = list(graph.successors(cursor))
            if len(successors) < 2:
                break
            total = sum(
                graph.edges[cursor, target].get("tainted_amount_raw", 0) for target in successors
            )
            if total <= 0:
                break
            main = max(
                successors, key=lambda t: graph.edges[cursor, t].get("tainted_amount_raw", 0)
            )
            carried = graph.edges[cursor, main].get("tainted_amount_raw", 0) / total
            if carried < config["min_carried"] or 1 - carried > config["max_peel"]:
                break
            hashes += graph.edges[cursor, main].get("tx_hashes", [])
            peeled += total - graph.edges[cursor, main].get("tainted_amount_raw", 0)
            chain.append(main)
            cursor = main
            if cursor in chain[:-1]:
                break

        if len(chain) >= config["min_length"]:
            visited.update(chain)
            findings.append(
                Finding(
                    pattern_type=PatternType.PEEL_CHAIN,
                    severity=severity_from(len(chain), medium=4, high=6),
                    subject_address=start,
                    involved_addresses=chain,
                    trigger_tx_hashes=list(dict.fromkeys(hashes)),
                    metrics={"chain_length": len(chain), "peeled_raw": str(int(peeled))},
                    explanation=(
                        f"Funds moved through a chain of {len(chain)} addresses, each "
                        f"forwarding most of the value onward and leaving a small amount "
                        f"behind. Peeling spreads funds thinly across many addresses while "
                        f"keeping the main flow moving."
                    ),
                )
            )
    return findings


@register(
    PatternType.DORMANCY_BURST,
    config={"min_dormant_days": 30, "burst_transfers": 3, "burst_hours": 24},
    false_positive_note=(
        "A long-term holder moving funds, a cold wallet being rotated, or an exchange "
        "reactivating an old address all look exactly like this. Dormancy followed by "
        "activity is unremarkable on its own."
    ),
)
def dormancy_burst(subject: Subject, config: dict[str, Any]) -> list[Finding]:
    """A long-quiet address that suddenly moves a lot in a short window."""
    findings = []
    for address in subject.graph.nodes:
        activity = sorted(subject.touching(address), key=lambda t: t.block_time)
        if len(activity) < config["burst_transfers"] + 1:
            continue

        gap = timedelta(days=config["min_dormant_days"])
        window = timedelta(hours=config["burst_hours"])
        for i in range(1, len(activity)):
            if activity[i].block_time - activity[i - 1].block_time < gap:
                continue
            burst = [t for t in activity[i:] if t.block_time - activity[i].block_time <= window]
            if len(burst) < config["burst_transfers"]:
                continue
            dormant_days = (activity[i].block_time - activity[i - 1].block_time).days
            findings.append(
                Finding(
                    pattern_type=PatternType.DORMANCY_BURST,
                    severity=severity_from(dormant_days, medium=90, high=365),
                    subject_address=address,
                    involved_addresses=sorted(
                        {t.to_address for t in burst} | {t.from_address for t in burst}
                    ),
                    trigger_tx_hashes=[t.tx_hash for t in burst],
                    metrics={"dormant_days": dormant_days, "burst_transfers": len(burst)},
                    explanation=(
                        f"{address} was inactive for {dormant_days} days, then made "
                        f"{len(burst)} transfers within {config['burst_hours']} hours."
                    ),
                )
            )
            break
    return findings


@register(
    PatternType.STRUCTURING,
    config={"min_count": 3, "window_hours": 24},
    false_positive_note=(
        "There is no on-chain reporting threshold to structure around, so this detector "
        "names a shape and nothing more. Automated equal-split payouts, recurring "
        "payments and dollar-cost-averaging bots all send repeated near-identical "
        "amounts. This must never be presented as a finding of structuring in the legal "
        "sense."
    ),
)
def structuring(subject: Subject, config: dict[str, Any]) -> list[Finding]:
    """Repeated near-identical amounts, split rather than sent in one movement."""
    findings = []
    for address in subject.graph.nodes:
        outbound = _within_window(subject.outbound(address), config["window_hours"])
        if len(outbound) < config["min_count"]:
            continue
        # Exact repetition of a raw amount is the shape; near-identical amounts differ by
        # fees that do not appear in a transfer's value, so exactness is not too strict.
        counts = Counter(t.amount_raw for t in outbound)
        amount, repeats = counts.most_common(1)[0]
        if repeats < config["min_count"]:
            continue
        matching = [t for t in outbound if t.amount_raw == amount]
        findings.append(
            Finding(
                pattern_type=PatternType.STRUCTURING,
                severity=severity_from(repeats, medium=5, high=10),
                subject_address=address,
                involved_addresses=sorted({t.to_address for t in matching}),
                trigger_tx_hashes=[t.tx_hash for t in matching],
                metrics={"repeat_count": repeats, "amount_raw": str(amount)},
                explanation=(
                    f"{address} sent the same amount {repeats} times within "
                    f"{config['window_hours']} hours, rather than moving the total in one "
                    f"transfer."
                ),
            )
        )
    return findings


def _within_window(transfers: list[Any], hours: int) -> list[Any]:
    """The densest run of transfers inside a rolling window of `hours`."""
    if not transfers:
        return []
    window = timedelta(hours=hours)
    best: list[Any] = []
    for i, anchor in enumerate(transfers):
        run = [t for t in transfers[i:] if t.block_time - anchor.block_time <= window]
        if len(run) > len(best):
            best = run
    return best


# Named so a caller can run a subset, and so the MVP three are visible as a group.
MUST_HAVE = (fan_out, fan_in, rapid_transfer)
SHOULD_HAVE = (peel_chain, dormancy_burst, structuring)
