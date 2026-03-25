import base64
import hashlib
import os
from datetime import datetime, timedelta, UTC
from typing import Any

import json
import argon2
from argon2 import PasswordHasher
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from jose import jwt
from fastapi import HTTPException

from common.core.config import settings

# Argon2id hasher configuration for passwords (random salt)
ph = PasswordHasher(
    time_cost=2,      # iterations
    memory_cost=65536, # 64MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=argon2.low_level.Type.ID
)

def get_password_hash(password: str) -> str:
    """Argon2id 비밀번호 해싱"""
    return ph.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Argon2id 비밀번호 검증"""
    try:
        return ph.verify(hashed_password, plain_password)
    except Exception:
        return False

def get_email_hash(email: str) -> str:
    """이메일 검색용 결정론적 Argon2id 해시"""
    # 검색을 위해 고정된 솔트를 사용하여 결정론적 해시 생성
    static_salt = settings.EMAIL_HASH_SALT.encode()
    # argon2.low_level.hash_secret_raw를 사용하여 직접 해싱 (고정 솔트 적용)
    hash_value = argon2.low_level.hash_secret_raw(
        secret=email.lower().encode(),
        salt=static_salt,
        time_cost=2,
        memory_cost=65536,
        parallelism=4,
        hash_len=32,
        type=argon2.low_level.Type.ID
    )
    return base64.b64encode(hash_value).decode('utf-8')

def encrypt_data(data: str) -> bytes:
    """AES-256-GCM 데이터 암호화"""
    try:
        key = base64.b64decode(settings.ENCRYPTION_KEY)
    except Exception as e:
        raise ValueError(f"Invalid ENCRYPTION_KEY format. Must be a valid Base64 string: {e}")
    
    if len(key) != 32:
        raise ValueError(f"Invalid ENCRYPTION_KEY length. Must be 32 bytes after decoding, but got {len(key)} bytes.")
    
    nonce = get_random_bytes(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(data.encode())
    # nonce, tag, ciphertext를 결합하여 저장
    return nonce + tag + ciphertext

def decrypt_data(encrypted_data: bytes) -> str:
    """AES-256-GCM 데이터 복호화"""
    try:
        key = base64.b64decode(settings.ENCRYPTION_KEY)
    except Exception as e:
        raise ValueError(f"Invalid ENCRYPTION_KEY format. Must be a valid Base64 string: {e}")
    
    # AES-GCM: nonce(12) + tag(16) + ciphertext
    if len(encrypted_data) < 28:
        return "decryption-failed-too-short"

    nonce = encrypted_data[:12]
    tag = encrypted_data[12:28]
    ciphertext = encrypted_data[28:]
    
    try:
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        decrypted_data = cipher.decrypt_and_verify(ciphertext, tag)
        return decrypted_data.decode()
    except Exception as e:
        return f"decryption-failed: {str(e)}"


def encrypt_float_list(float_list: list[float]) -> bytes:
    """list[float]를 JSON으로 직렬화하여 AES-256-GCM 암호화"""
    try:
        key = base64.b64decode(settings.ENCRYPTION_KEY)
    except Exception as e:
        raise ValueError(f"Invalid ENCRYPTION_KEY format: {e}")

    if len(key) != 32:
        raise ValueError(f"Invalid key length: {len(key)} bytes.")

    # 1. 리스트를 JSON 문자열로 변환 후 바이트로 인코딩
    json_data = json.dumps(float_list)
    byte_data = json_data.encode('utf-8')

    nonce = get_random_bytes(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)

    # 2. 암호화 진행
    ciphertext, tag = cipher.encrypt_and_digest(byte_data)

    return nonce + tag + ciphertext


def decrypt_float_list(encrypted_data: bytes) -> list[float]:
    """암호화된 데이터를 복호화하여 다시 list[float]로 복구"""
    key = base64.b64decode(settings.ENCRYPTION_KEY)

    nonce = encrypted_data[:12]
    tag = encrypted_data[12:28]
    ciphertext = encrypted_data[28:]

    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    # 복호화 및 검증
    decrypted_byte_data = cipher.decrypt_and_verify(ciphertext, tag)

    # 3. 바이트 -> 문자열 -> 리스트 역직렬화
    return json.loads(decrypted_byte_data.decode('utf-8'))

def mask_email(email: str) -> str:
    """이메일 마스킹 처리 (예: jh***@gmail.com)"""
    try:
        user_part, domain_part = email.split("@")
        if len(user_part) <= 2:
            masked_user = "*" * len(user_part)
        else:
            masked_user = user_part[:2] + "*" * (len(user_part) - 2)
        return f"{masked_user}@{domain_part}"
    except Exception:
        return "invalid-email"

def create_access_token(subject: str | Any, expires_delta: timedelta | None = None) -> str:
    """Access Token 생성"""
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "exp": expire, 
        "sub": str(subject), 
        "iss": settings.JWT_ISSUER,
        "type": "access"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token(subject: str | Any, expires_delta: timedelta | None = None) -> str:
    """Refresh Token 생성"""
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "exp": expire, 
        "sub": str(subject), 
        "iss": settings.JWT_ISSUER,
        "type": "refresh"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt
