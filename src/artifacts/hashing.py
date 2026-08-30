from __future__ import annotations

import hashlib


def compute_bytes_hash(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
