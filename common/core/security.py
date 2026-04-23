import base64
import hashlib
import os
from datetime import datetime, timedelta, UTC
from typing import Any
import array
import zstandard as zstd


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


def compress_and_encrypt_int_list(int_list: list[int]) -> bytes:
    """list[float]를 바이너리화 -> Zstandard 압축 -> AES-256-GCM 암호화"""
    try:
        key = base64.b64decode(settings.ENCRYPTION_KEY)
    except Exception as e:
        raise ValueError(f"Invalid ENCRYPTION_KEY format: {e}")

    if len(key) != 32:
        raise ValueError(f"Invalid key length: {len(key)} bytes.")

    byte_data = array.array('h', int_list).tobytes()

    # ---------------------------------------------------------
    # 2. 압축 (반드시 암호화 전에 수행!)
    # ---------------------------------------------------------
    compressor = zstd.ZstdCompressor(level=3)
    compressed_data = compressor.compress(byte_data)

    # ---------------------------------------------------------
    # 3. 암호화 진행 (압축된 데이터 기반)
    # ---------------------------------------------------------
    nonce = get_random_bytes(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)

    # byte_data가 아닌 compressed_data를 암호화합니다.
    ciphertext, tag = cipher.encrypt_and_digest(compressed_data)

    # 최종 bytes 반환 (DB의 LargeBinary 컬럼으로 직행)
    return nonce + tag + ciphertext

def compress_and_encrypt_float_list(float_list: list[float]) -> bytes:
    """list[float]를 바이너리화 -> Zstandard 압축 -> AES-256-GCM 암호화"""
    try:
        key = base64.b64decode(settings.ENCRYPTION_KEY)
    except Exception as e:
        raise ValueError(f"Invalid ENCRYPTION_KEY format: {e}")

    if len(key) != 32:
        raise ValueError(f"Invalid key length: {len(key)} bytes.")

    byte_data = array.array('f', float_list).tobytes()

    # ---------------------------------------------------------
    # 2. 압축 (반드시 암호화 전에 수행!)
    # ---------------------------------------------------------
    compressor = zstd.ZstdCompressor(level=3)
    compressed_data = compressor.compress(byte_data)

    # ---------------------------------------------------------
    # 3. 암호화 진행 (압축된 데이터 기반)
    # ---------------------------------------------------------
    nonce = get_random_bytes(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)

    # byte_data가 아닌 compressed_data를 암호화합니다.
    ciphertext, tag = cipher.encrypt_and_digest(compressed_data)

    # 최종 bytes 반환 (DB의 LargeBinary 컬럼으로 직행)
    return nonce + tag + ciphertext


# (참고) settings.ENCRYPTION_KEY 가 있다고 가정

def decrypt_and_decompress_float_list(encrypted_data: bytes) -> list[float]:
    """AES-256-GCM 복호화 -> Zstandard 압축 해제 -> list[float] 복원"""

    # 0. 키 준비 (암호화 때와 동일)
    try:
        key = base64.b64decode(settings.ENCRYPTION_KEY)
    except Exception as e:
        raise ValueError(f"Invalid ENCRYPTION_KEY format: {e}")

    if len(key) != 32:
        raise ValueError(f"Invalid key length: {len(key)} bytes.")

    # ---------------------------------------------------------
    # 1. 데이터 분리 (Slicing)
    # 저장할 때 return nonce(12) + tag(16) + ciphertext 형태였음
    # PyCryptodome의 GCM tag 기본 길이는 16바이트입니다.
    # ---------------------------------------------------------
    if len(encrypted_data) < 28:
        raise ValueError("Data is too short to contain nonce, tag, and ciphertext.")

    nonce = encrypted_data[:12]
    tag = encrypted_data[12:28]
    ciphertext = encrypted_data[28:]

    # ---------------------------------------------------------
    # 2. 복호화 및 무결성 검증 (AES-GCM)
    # ---------------------------------------------------------
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)

    try:
        # decrypt_and_verify는 복호화와 동시에 데이터가 변조되지 않았는지(tag) 확인합니다.
        compressed_data = cipher.decrypt_and_verify(ciphertext, tag)
    except ValueError as e:
        # 키가 틀렸거나 데이터가 DB에서 손상/변조된 경우 발생합니다.
        raise ValueError("Decryption failed or data was corrupted/tampered.") from e

    # ---------------------------------------------------------
    # 3. Zstandard 압축 해제
    # ---------------------------------------------------------
    decompressor = zstd.ZstdDecompressor()
    try:
        byte_data = decompressor.decompress(compressed_data)
    except zstd.ZstdError as e:
        raise ValueError("Decompression failed. Data might be corrupted.") from e

    # ---------------------------------------------------------
    # 4. 순수 C 배열(Bytes)을 파이썬 list[float]로 복원
    # 암호화 시 array('f')를 사용했으므로 동일하게 'f'로 읽어옵니다.
    # ---------------------------------------------------------
    float_array = array.array('f')
    float_array.frombytes(byte_data)

    return float_array.tolist()


def decrypt_and_decompress_int_list(encrypted_data: bytes) -> list[int]:
    """AES-256-GCM 복호화 -> Zstandard 압축 해제 -> list[int] 복원"""

    # 0. 키 준비
    try:
        key = base64.b64decode(settings.ENCRYPTION_KEY)
    except Exception as e:
        raise ValueError(f"Invalid ENCRYPTION_KEY format: {e}")

    if len(key) != 32:
        raise ValueError(f"Invalid key length: {len(key)} bytes.")

    # 1. 데이터 분리 (Slicing)
    if len(encrypted_data) < 28:
        raise ValueError("Data is too short to contain nonce, tag, and ciphertext.")

    nonce = encrypted_data[:12]
    tag = encrypted_data[12:28]
    ciphertext = encrypted_data[28:]

    # 2. 복호화 및 무결성 검증 (AES-GCM)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    try:
        compressed_data = cipher.decrypt_and_verify(ciphertext, tag)
    except ValueError as e:
        raise ValueError("Decryption failed or data was corrupted/tampered.") from e

    # 3. Zstandard 압축 해제
    decompressor = zstd.ZstdDecompressor()
    try:
        byte_data = decompressor.decompress(compressed_data)
    except zstd.ZstdError as e:
        raise ValueError("Decompression failed. Data might be corrupted.") from e

    # ---------------------------------------------------------
    # 🌟 4. 핵심 변경 포인트: 순수 C 배열을 파이썬 list[int]로 복원
    # 암호화 시 array('h')를 사용했다면 여기서도 반드시 'h'를 사용해야 합니다!
    # (만약 암호화 때 4바이트 'i'를 썼다면, 여기서도 'i'로 맞춰야 에러가 안 납니다.)
    # ---------------------------------------------------------
    int_array = array.array('h')
    int_array.frombytes(byte_data)

    return int_array.tolist()

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

def create_user_access_token(data: dict | Any, expires_delta: timedelta | None = None) -> str:
    """Access Token 생성"""

    sub = data.get("userId")
    permissions = data.get("permissions")

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "exp": expire, 
        "sub": sub,
        "permissions": permissions,
        "iss": settings.JWT_ISSUER,
        "type": "access"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_user_refresh_token(data: dict | Any, expires_delta: timedelta | None = None) -> str:
    """Refresh Token 생성"""

    sub = data.get("userId")
    permissions = data.get("permissions")

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "exp": expire, 
        "sub": sub,
        "permissions": permissions,
        "iss": settings.JWT_ISSUER,
        "type": "refresh"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_patient_access_token(data: dict | Any, expires_delta: timedelta | None = None) -> str:
    """Access Token 생성"""

    sub = data.get("PatientId")

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "exp": expire,
        "sub": sub,
        "iss": settings.JWT_ISSUER,
        "type": "access"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_patient_refresh_token(data: dict | Any, expires_delta: timedelta | None = None) -> str:
    """Refresh Token 생성"""

    sub = data.get("PatientId")
    permissions = data.get("permissions")

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "exp": expire,
        "sub": sub,
        "iss": settings.JWT_ISSUER,
        "type": "refresh"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt