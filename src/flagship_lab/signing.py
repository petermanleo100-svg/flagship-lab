from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Protocol

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


@dataclass(frozen=True)
class Signature:
    algorithm: str
    key_id: str
    value: str


class EvidenceSigner(Protocol):
    def sign(self, material: bytes) -> Signature: ...


class Ed25519Signer:
    def __init__(self, private_key_pem: str | bytes, key_id: str):
        pem = private_key_pem.encode() if isinstance(private_key_pem, str) else private_key_pem
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("evidence signing key must be an Ed25519 private key")
        self.key = key
        self.key_id = key_id

    def sign(self, material: bytes) -> Signature:
        return Signature("Ed25519", self.key_id, base64.b64encode(self.key.sign(material)).decode())


class AwsKmsSigner:
    """AWS KMS asymmetric signer; private key material never enters the process."""

    def __init__(self, kms_client, key_id: str, signing_algorithm: str = "ECDSA_SHA_256"):
        self.client = kms_client
        self.key_id = key_id
        self.signing_algorithm = signing_algorithm

    def sign(self, material: bytes) -> Signature:
        response = self.client.sign(KeyId=self.key_id, Message=material, MessageType="RAW",
                                    SigningAlgorithm=self.signing_algorithm)
        return Signature(self.signing_algorithm, response.get("KeyId", self.key_id),
                         base64.b64encode(response["Signature"]).decode())
