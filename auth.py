"""
auth.py — password hashing (pbkdf2, เหมือน Checker api.py เป๊ะ) + JWT
"""
import os
import time
import hashlib
import secrets
import jwt

JWT_SECRET       = os.getenv("SM_JWT_SECRET", "CHANGE-THIS-SECRET-BEFORE-DEPLOY")
JWT_ALG          = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("SM_JWT_EXPIRE_HOURS", "12"))


def hash_pw(pw: str, salt: str = None, iters: int = 200000) -> str:
    """ห้ามแก้ format นี้ — sm_users ถูก seed มาด้วย hash แบบนี้ (seed_sm_users.py)"""
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), iters)
    return f"pbkdf2$sha256${iters}${salt}${dk.hex()}"


def verify_pw(pw: str, stored_hash: str) -> bool:
    try:
        _algo, _hashname, iters, salt, hexhash = stored_hash.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), int(iters))
        return secrets.compare_digest(dk.hex(), hexhash)
    except Exception:
        return False


def create_token(username: str) -> str:
    payload = {"sub": username, "exp": int(time.time()) + JWT_EXPIRE_HOURS * 3600}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
