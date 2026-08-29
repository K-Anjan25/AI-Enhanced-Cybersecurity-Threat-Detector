"""Field-level encryption for credentials this app stores at rest.

Connector configuration holds two secrets per source: an outbound credential
(the header value used when polling a provider) and an inbound shared secret
(the token a provider must present when pushing events). Storing either in
cleartext means a database dump, a leaked backup or a stray ``SELECT`` hands
over live provider credentials — in a product whose whole pitch is handling
security telemetry carefully.

The key is derived from ``JWT_SECRET_KEY`` rather than introduced as a second
secret to distribute: it is already required in every environment, and the k8s
configmap does not need a new entry. The trade-off is explicit and deliberate —
**rotating JWT_SECRET_KEY invalidates stored connector credentials**, and each
source must have its secret re-entered. That is the correct failure mode: a
credential that cannot be decrypted is reported as such, never silently
downgraded to "no credential configured".

Ciphertext is tagged (``enc:v1:``) so a future key rotation or algorithm change
can be recognised, and so a value that fails to decrypt is distinguishable from
one that was never encrypted.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_PREFIX = "enc:v1:"

# Domain separator: the connector-credentials key must not be the same bytes as
# any other use of JWT_SECRET_KEY.
_LABEL = b"noctra.connector-credentials.v1"


class SecretDecryptionError(Exception):
    """A stored credential exists but cannot be decrypted with the current key.

    Raised instead of returning None: "I cannot read this secret" and "no
    secret is configured" are different states and must not collapse into one.
    """


def _fernet() -> Fernet:
    material = hashlib.sha256(_LABEL + settings.JWT_SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def encrypt_secret(value: str | None) -> str | None:
    """Encrypt for storage. Empty/None stays None — there is no secret."""
    if value is None or value == "":
        return None
    return _PREFIX + _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(stored: str | None) -> str | None:
    """Decrypt a stored credential.

    Returns None when nothing is stored. Raises SecretDecryptionError when
    something is stored but the key no longer opens it (JWT_SECRET_KEY was
    rotated), so the caller can say so instead of treating it as unset.
    """
    if stored is None:
        return None
    if not stored.startswith(_PREFIX):
        # Written before encryption existed. There is no released data in this
        # state — the connector table shipped encrypted — so this is a schema
        # violation rather than a migration path.
        raise SecretDecryptionError("stored credential is not in a recognised format")

    try:
        return _fernet().decrypt(stored[len(_PREFIX) :].encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretDecryptionError(
            "stored credential cannot be decrypted with the current JWT_SECRET_KEY"
        ) from exc
