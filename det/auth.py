"""Manager passcode. A convenience gate for the interface, not security: anyone who can open the
shared folder can read the data files directly."""
from __future__ import annotations

import hashlib
import hmac
import os

ROUNDS = 200_000


def hash_passcode(code: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac('sha256', code.encode('utf-8'), salt, ROUNDS)
    return f'pbkdf2${ROUNDS}${salt.hex()}${digest.hex()}'


def check_passcode(code: str, stored: str) -> bool:
    try:
        scheme, rounds, salt, digest = stored.split('$')
        if scheme != 'pbkdf2':
            return False
        candidate = hashlib.pbkdf2_hmac('sha256', code.encode('utf-8'), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(candidate.hex(), digest)
    except (ValueError, AttributeError):
        return False
