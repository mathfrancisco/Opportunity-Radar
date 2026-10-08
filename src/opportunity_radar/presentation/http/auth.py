"""Fail-closed Clerk JWT verification at the HTTP boundary."""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any, NoReturn
from urllib.parse import urlparse

import jwt
from fastapi import HTTPException, Request, status
from jwt import (
    ExpiredSignatureError,
    InvalidIssuerError,
    InvalidTokenError,
    MissingRequiredClaimError,
)

from opportunity_radar.platform.logging import CORRELATION_ID, get_logger

logger = get_logger("opportunity_radar.http.auth")


class AuthenticationError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class RequestIdentity:
    sub: str
    is_owner: bool


@dataclass(frozen=True)
class AuthConfig:
    issuer: str
    jwks_url: str
    authorized_parties: frozenset[str]
    owner_sub: str

    def __post_init__(self) -> None:
        issuer = urlparse(self.issuer)
        jwks = urlparse(self.jwks_url)
        if not self.authorized_parties or not self.owner_sub.strip():
            raise ValueError("authorized parties and owner subject are required")
        if issuer.scheme != "https" or not issuer.netloc:
            raise ValueError("CLERK_ISSUER must be an HTTPS URL")
        if (
            jwks.scheme != "https"
            or not jwks.netloc
            or (jwks.scheme, jwks.netloc)
            != (
                issuer.scheme,
                issuer.netloc,
            )
        ):
            raise ValueError("CLERK_JWKS_URL must be HTTPS and belong to CLERK_ISSUER")


JwksTransport = Callable[[str, float, int], bytes]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def _fetch_jwks(url: str, timeout_seconds: float, max_bytes: int) -> bytes:
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with opener.open(request, timeout=timeout_seconds) as response:  # nosec B310 -- URL is validated config
            if int(response.headers.get("Content-Length", "0")) > max_bytes:
                raise ValueError("too large")
            body = response.read(max_bytes + 1)
    except Exception as error:
        raise AuthenticationError("jwks_unavailable") from error
    if len(body) > max_bytes:
        raise AuthenticationError("jwks_unavailable")
    return body


class JwksClient:
    def __init__(
        self, url: str, *, transport: JwksTransport = _fetch_jwks, ttl_seconds: float = 300
    ) -> None:
        self._url, self._transport, self._ttl_seconds = url, transport, ttl_seconds
        self._keys: dict[str, dict[str, Any]] = {}
        self._expires_at = 0.0
        self._lock = Lock()

    def get(self, kid: str) -> dict[str, Any]:
        with self._lock:
            if time.monotonic() >= self._expires_at:
                self._refresh()
            key = self._keys.get(kid)
            if key is None:
                raise AuthenticationError("jwks_unknown_kid")
            return key

    def _refresh(self) -> None:
        try:
            keys = json.loads(self._transport(self._url, 2.0, 1_000_000))["keys"]
            if not isinstance(keys, list) or not keys or len(keys) > 32:
                raise ValueError("invalid keys")
            parsed = {
                key["kid"]: key
                for key in keys
                if isinstance(key, dict)
                and isinstance(key.get("kid"), str)
                and key.get("kty") == "RSA"
                and key.get("use") in (None, "sig")
                and "d" not in key
            }
            if len(parsed) != len(keys):
                raise ValueError("invalid keys")
        except Exception as error:
            self._keys = {}
            raise AuthenticationError("jwks_unavailable") from error
        self._keys, self._expires_at = parsed, time.monotonic() + self._ttl_seconds


class JwtVerifier:
    def __init__(self, config: AuthConfig, jwks: JwksClient) -> None:
        self.config, self._jwks = config, jwks

    def verify(self, token: str) -> RequestIdentity:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise AuthenticationError("malformed_token")
            jwk = self._jwks.get(header["kid"])
            key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                issuer=self.config.issuer,
                options={"require": ["exp", "iss", "sub", "azp"]},
            )
        except AuthenticationError:
            raise
        except (
            ExpiredSignatureError,
            InvalidIssuerError,
            MissingRequiredClaimError,
            InvalidTokenError,
        ) as error:
            raise AuthenticationError("invalid_token") from error
        except Exception as error:
            raise AuthenticationError("invalid_token") from error
        subject, party = claims.get("sub"), claims.get("azp")
        if (
            not isinstance(subject, str)
            or not subject
            or not isinstance(party, str)
            or party not in self.config.authorized_parties
        ):
            raise AuthenticationError("invalid_token")
        return RequestIdentity(sub=subject, is_owner=subject == self.config.owner_sub)


class RequireAuthenticated:
    def __init__(self, verifier: JwtVerifier) -> None:
        self._verifier = verifier

    def __call__(self, request: Request) -> RequestIdentity:
        authorization = request.headers.get("Authorization")
        if authorization is None:
            self._reject("missing_authorization")
        scheme, separator, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not separator or not token or token.strip() != token:
            self._reject("malformed_authorization")
        try:
            return self._verifier.verify(token)
        except AuthenticationError as error:
            self._reject(error.reason)

    @staticmethod
    def _log(reason: str) -> None:
        logger.warning(
            "authentication denied",
            extra={"auth_reason": reason, "correlation_id": CORRELATION_ID.get()},
        )

    @classmethod
    def _reject(cls, reason: str) -> NoReturn:
        cls._log(reason)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )


class RequireOwner:
    def __init__(self, authenticated: RequireAuthenticated) -> None:
        self._authenticated = authenticated

    def __call__(self, request: Request) -> RequestIdentity:
        identity = self._authenticated(request)
        if not identity.is_owner:
            logger.warning(
                "authorization denied",
                extra={"auth_reason": "owner_required", "correlation_id": CORRELATION_ID.get()},
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return identity
