"""Create the RSA key pair DATAMIND_APP signs in with (key-pair auth, no password).

    python scripts/make_keypair.py                  # -> keys/rsa_key.p8 (private, git-ignored)
    python scripts/make_keypair.py --passphrase     # encrypt the private key; put the passphrase in .env

Prints the ALTER USER statement to run once in Snowsight as ACCOUNTADMIN. Never commit keys/.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parent.parent


def make(out_dir: Path, passphrase: str | None, force: bool = False) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    private = out_dir / "rsa_key.p8"
    if private.exists() and not force:
        sys.exit(f"{private} already exists; use --force to replace it (the old key stops working)")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    enc = (serialization.BestAvailableEncryption(passphrase.encode()) if passphrase
           else serialization.NoEncryption())
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, enc))
    private.chmod(0o600)
    pub = key.public_key().public_bytes(serialization.Encoding.PEM,
                                        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    (out_dir / "rsa_key.pub").write_text(pub)
    return "".join(l for l in pub.splitlines() if "-----" not in l)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--passphrase", action="store_true", help="encrypt the private key with a passphrase")
    ap.add_argument("--force", action="store_true", help="replace an existing key")
    ap.add_argument("--user", default="DATAMIND_APP")
    a = ap.parse_args()
    pp = getpass.getpass("Passphrase for the private key: ") if a.passphrase else None
    body = make(ROOT / "keys", pp, a.force)
    print(f"Private key: {ROOT / 'keys' / 'rsa_key.p8'} (keep it secret; it is git-ignored)\n")
    print("Run this once in a Snowsight worksheet as ACCOUNTADMIN:\n")
    print(f"ALTER USER {a.user} SET RSA_PUBLIC_KEY = '{body}';")
