"""Partition assignment by `src_ip` (T-306, architecture.md:135).

Ordering within Kafka is per partition, and only per partition. So "one
entity's flows stay ordered" is not a property of the broker -- it is a
property of *which partition a record is sent to*. Two flows from the same
source that land on different partitions have no ordering guarantee between
them, however correct the broker is.

That makes the partitioner the thing that has to be right, and it has to agree
with what a real broker computes. So this module delegates to Kafka's own
default partitioner rather than reimplementing it: a hand-rolled hash would
still be deterministic, and would still be wrong, and the disagreement would
only show up as out-of-order scoring after a rebalance.

**Stability across a restart is the point.** The mapping is a pure function of
the key and the partition count, with no state, so a producer that restarts
assigns the same partition to the same `src_ip`. If the partition count
changes, the mapping changes for most keys -- which is why the count is
configuration and not something to change casually.
"""

from __future__ import annotations

from kafka.partitioner import DefaultPartitioner  # type: ignore[import-untyped]

__all__ = ["FLOW_TOPIC", "partition_for", "partition_key"]

#: architecture.md:135.
FLOW_TOPIC = "flows.raw"

_partitioner = DefaultPartitioner()


def partition_key(src_ip: str) -> bytes:
    """The partition key for a flow: its source address, as bytes.

    The key is the `src_ip` alone, deliberately. Adding anything else -- a port,
    a timestamp -- would split one entity's flows across partitions and lose the
    ordering this module exists to provide.
    """
    return src_ip.encode()


def partition_for(src_ip: str, num_partitions: int, available: list[int] | None = None) -> int:
    """The partition one source address maps to.

    Args:
        src_ip: the flow's source address.
        num_partitions: how many partitions the topic has.
        available: partitions currently available, when a rebalance has made
            some unavailable. Defaults to all of them.

    Returns:
        The partition index. The same inputs always give the same answer.

    Raises:
        ValueError: if the topic has no partitions, since there is nowhere to
            send the record and silently dropping it would be worse.
    """
    if num_partitions <= 0:
        msg = f"a topic needs at least one partition, got {num_partitions}"
        raise ValueError(msg)
    partitions = available if available is not None else list(range(num_partitions))
    if not partitions:
        msg = "no partitions are available to send to"
        raise ValueError(msg)
    return int(_partitioner(partition_key(src_ip), partitions, []))
