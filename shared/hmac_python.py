"""
HMAC-SHA256 签名工具 — Python 版

用于 gold-team (Python) 和 review-platform (Python) 的回调签名/验证。

用法:
    签名: signature = sign(body_bytes, secret)
    验证: verify(body_bytes, secret, received_header)
"""

import hmac
import hashlib
import os


def sign(body: bytes, secret: str) -> str:
    """生成 HMAC-SHA256 签名，返回 header 值格式: sha256={hex}"""
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def verify(body: bytes, secret: str, header_value: str) -> bool:
    """
    验证 HMAC-SHA256 签名。
    body: 原始请求 body (bytes)
    secret: 共享密钥
    header_value: X-HMAC-Signature header 的值，格式 "sha256={hex}"
    """
    if not header_value or not header_value.startswith("sha256="):
        return False
    expected = sign(body, secret)
    return hmac.compare_digest(expected, header_value)


def get_secret(env_var: str) -> str:
    """从环境变量读取密钥，缺失时抛出明确错误。"""
    secret = os.environ.get(env_var)
    if not secret:
        raise ValueError(f"环境变量 {env_var} 未设置")
    if secret == "change-me-in-production":
        raise ValueError(f"环境变量 {env_var} 仍为默认值，请替换为安全密钥")
    return secret
