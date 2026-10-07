"""Identity primitives shared by credential services and wire schemas."""

from __future__ import annotations


def normalise_email(email: str) -> str:
    """Trim and case-fold an address, refusing an unusable login identifier."""
    normalised = email.strip().casefold()
    local, separator, domain = normalised.partition("@")
    if (
        not separator
        or not local
        or not domain
        or "@" in domain
        or any(character.isspace() for character in normalised)
        or len(normalised) > 254
    ):
        raise ValueError("email must be a valid address")
    return normalised
