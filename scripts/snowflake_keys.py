"""Create key pairs for the Planwerk Snowflake service users and render the bootstrap SQL.

    python scripts/snowflake_keys.py [--out keys]

Writes keys/planwerk_ci.p8, keys/planwerk_assistant.p8 (private, never commit; keys/ is
gitignored) and keys/bootstrap.rendered.sql (contains only public keys, safe to paste).
Existing private keys are reused, so re-running only re-renders the SQL.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
USERS = {"PLANWERK_CI": "planwerk_ci", "PLANWERK_ASSISTANT": "planwerk_assistant"}


def ensure_key(path: Path) -> str:
    if path.exists():
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
        path.chmod(0o600)
    pub = key.public_key().public_bytes(serialization.Encoding.PEM,
                                        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return "".join(line for line in pub.splitlines() if "PUBLIC KEY" not in line)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "keys")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    sql = (ROOT / "infra" / "snowflake" / "bootstrap.sql").read_text()
    for user, stem in USERS.items():
        sql = sql.replace(f"<{user}_PUBLIC_KEY>", ensure_key(a.out / f"{stem}.p8"))
    (a.out / "bootstrap.rendered.sql").write_text(sql)
    print(f"wrote {a.out / 'bootstrap.rendered.sql'}")


if __name__ == "__main__":
    main()
