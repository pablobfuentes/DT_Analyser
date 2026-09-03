import hashlib
import json
from decimal import Decimal
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint_from_parts(*parts: Any) -> str:
    normalized = []
    for p in parts:
        if p is None:
            normalized.append("")
        elif isinstance(p, Decimal):
            normalized.append(format(p, "f"))
        else:
            normalized.append(str(p))
    payload = "|".join(normalized)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def json_dumps(obj: Any) -> str:
    def default(o):
        if isinstance(o, Decimal):
            return str(o)
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")

    return json.dumps(obj, default=default, ensure_ascii=False)
