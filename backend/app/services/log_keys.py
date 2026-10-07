"""How a log line is addressed as a cluster (T-407, T-419).

One definition, used by three places that must agree:

* the live tail folds a batch into rows by it (T-407);
* the log store writes it as a column when a line is accepted (T-419), so a stored
  read and a live read name the same clusters;
* the store groups and filters by it, which is a plain indexed equality rather
  than a digest recomputed per row per query.

It lives in its own module because the alternative was a second copy, and two
copies of "what a cluster is" would drift the moment either side was edited --
the failure being a stored read that shows a row the live tail would never have
produced, which nothing on either screen would look wrong about.
"""

from __future__ import annotations

from hashlib import sha256

from app.schemas.ingest import LogRecordIn

__all__ = [
    "DIGEST_LENGTH",
    "MESSAGE_KEY_PREFIX",
    "cluster_key",
    "message_key",
]

#: The prefix that marks a cluster key as a message digest rather than a template id.
MESSAGE_KEY_PREFIX = "message:"

#: A digest is 12 hex characters: long enough that two distinct messages collide only
#: by a chosen collision, short enough to paste into a URL by hand.
DIGEST_LENGTH = 12


def message_key(message: str) -> str:
    """The cluster key for a line that carries no template id.

    A digest rather than the message: the key travels in a query string, and a
    query string ends up in an access log (R-58). It is stable for the same
    message, which is all a cluster key has to be.
    """
    digest = sha256(message.encode("utf-8")).hexdigest()[:DIGEST_LENGTH]
    return f"{MESSAGE_KEY_PREFIX}{digest}"


def cluster_key(record: LogRecordIn) -> str:
    """The cluster a line belongs to: its template id, or its message digest.

    An empty string is treated as no template id rather than as one of its own:
    a collector that sends ``""`` means "not mined", and a cluster named after
    nothing would collect every such line together.
    """
    template_id = (record.template_id or "").strip()
    return template_id if template_id else message_key(record.message)
