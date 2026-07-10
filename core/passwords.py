"""Password hashing with stdlib scrypt — no extra dependencies.

Stored format: "scrypt$<b64 salt>$<b64 digest>". Parameters follow the
OWASP scrypt recommendation (N=2^14, r=8, p=1).
"""

import base64
import hashlib
import hmac
import os

_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=64 * 1024 * 1024
    )
    return "scrypt${}${}".format(
        base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except (ValueError, TypeError):
        return False
    actual = hashlib.scrypt(
        password.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=64 * 1024 * 1024
    )
    return hmac.compare_digest(actual, expected)
