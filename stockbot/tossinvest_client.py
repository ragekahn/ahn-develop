"""Shared HTTP client for the Toss Securities (TossInvest) OpenAPI.

This module owns the OAuth2 client-credentials flow, token caching/refresh,
the account-resolution header (``X-Tossinvest-Account``), the market header
(``X-Tossinvest-Market``) and a tiny wrapper around the stdlib ``urllib`` so
the ``Broker`` and ``DataProvider`` adapters do not duplicate any of that.

It mirrors the style of ``stockbot.data.providers`` (stdlib ``urllib`` only,
no third-party HTTP dependency).

Endpoints used (TossInvest OpenAPI):
  * ``POST   /auth/token``                    -> access/refresh token
  * ``POST   /auth/refresh``                  -> rotated access token
  * ``GET    /accounts``                      -> list of trading accounts
  * ``GET    /prices/{symbol}``               -> latest price snapshot
  * ``GET    /candles/{symbol}?count=N``      -> OHLCV candles
  * ``GET    /accounts/{seq}/holdings``       -> holdings + cash
  * ``POST   /orders``                        -> place an order
  * ``DELETE /orders/{orderId}``              -> cancel an order

Field names follow the publicly documented TossInvest conventions. If your
tenant returns slightly different keys the adapters fall back to aliases.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .logger import get_logger

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 stockbot"
)


class TossInvestAPIError(RuntimeError):
    """Raised when the TossInvest API returns a non-2xx response."""


class TossInvestClient:
    """Thin, auth-aware client for the TossInvest OpenAPI."""

    DEFAULT_BASE_URL = "https://openapi.tossinvestment.se"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        base_url: Optional[str] = None,
        market: str = "KR",
        account_seq: Optional[int] = None,
        timeout: float = 20.0,
    ) -> None:
        self.log = get_logger()
        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self._market = market.upper()
        self._timeout = timeout
        self._explicit_account_seq = account_seq

        # token state
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expires_at: float = 0.0

        # account state
        self._account_seq: Optional[int] = account_seq
        self._account_no: Optional[str] = None
        self._account_currency: Optional[str] = None

    # -- public introspection -------------------------------------------
    @property
    def market(self) -> str:
        return self._market

    @property
    def account_seq(self) -> int:
        if self._account_seq is None:
            raise TossInvestAPIError("accountSeq is not resolved yet")
        return self._account_seq

    @property
    def account_no(self) -> Optional[str]:
        return self._account_no
    # -- auth -----------------------------------------------------------
    def _fetch_token(self) -> None:
        url = f"{self._base_url}/auth/token"
        body = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        data = self._raw("POST", url, body=body)
        if not isinstance(data, dict) or "access_token" not in data:
            raise TossInvestAPIError(f"unexpected /auth/token response: {data!r}")
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        try:
            expires_in = float(data.get("expires_in", 60))
        except (TypeError, ValueError):
            expires_in = 60.0
        self._token_expires_at = time.time() + max(expires_in - 5, 5)
        self.log.debug("TossInvest access token acquired (expires_in=%.0fs)", expires_in)

    def _refresh_access_token(self) -> None:
        if not self._refresh_token:
            self._fetch_token()
            return
        url = f"{self._base_url}/auth/refresh"
        body = {
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        data = self._raw("POST", url, body=body)
        if not isinstance(data, dict) or "access_token" not in data:
            self._fetch_token()
            return
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        try:
            expires_in = float(data.get("expires_in", 60))
        except (TypeError, ValueError):
            expires_in = 60.0
        self._token_expires_at = time.time() + max(expires_in - 5, 5)

    def ensure_token(self) -> None:
        if self._access_token and time.time() < self._token_expires_at:
            return
        self._fetch_token()

    # -- account resolution --------------------------------------------
    def ensure_account(self) -> None:
        if self._account_seq is not None:
            return
        self.ensure_token()
        data = self._request("GET", "/accounts", account=False)
        accounts = self._as_list(data)
        if not accounts:
            raise TossInvestAPIError("TossInvest /accounts returned no accounts")
        wanted = "KRW" if self._market == "KR" else "USD"
        chosen = next((a for a in accounts if a.get("currency") == wanted), None)
        chosen = chosen or accounts[0]
        self._account_seq = int(chosen["accountSeq"])
        self._account_no = chosen.get("accountNo") or chosen.get("account_no")
        self._account_currency = chosen.get("currency")
        self.log.info(
            "Resolved TossInvest account seq=%s no=%s currency=%s",
            self._account_seq, self._account_no, self._account_currency,
        )
    # -- high level request --------------------------------------------
    def get(self, path: str, market: Optional[str] = None, account: bool = True) -> Any:
        return self._request("GET", path, market=market, account=account)

    def post(
        self,
        path: str,
        body: Dict[str, Any],
        market: Optional[str] = None,
        account: bool = True,
    ) -> Any:
        return self._request("POST", path, body=body, market=market, account=account)

    def delete(self, path: str, market: Optional[str] = None, account: bool = True) -> Any:
        return self._request("DELETE", path, market=market, account=account)

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        market: Optional[str] = None,
        account: bool = True,
    ) -> Any:
        url = f"{self._base_url}{path}"
        self.ensure_token()
        headers = self._headers(market=market, account=account)
        try:
            return self._raw(method, url, body=body, headers=headers)
        except TossInvestAPIError as exc:
            if "401" in str(exc) and self._access_token is not None:
                self.log.warning("TossInvest 401, refreshing token and retrying")
                self._refresh_access_token()
                headers = self._headers(market=market, account=account)
                return self._raw(method, url, body=body, headers=headers)
            raise

    def _headers(self, market: Optional[str] = None, account: bool = True) -> Dict[str, str]:
        self.ensure_token()
        headers = {"Authorization": f"Bearer {self._access_token}"}
        if market:
            headers["X-Tossinvest-Market"] = market.upper()
        if account:
            self.ensure_account()
            headers["X-Tossinvest-Account"] = str(self._account_seq)
        return headers

    # -- response helpers ----------------------------------------------
    @staticmethod
    def _unwrap(data: Any) -> Any:
        if isinstance(data, dict) and ("data" in data or "result" in data):
            inner = data.get("data", data.get("result"))
            if inner is not None:
                return inner
        return data

    @classmethod
    def _as_list(cls, data: Any) -> List[Dict[str, Any]]:
        data = cls._unwrap(data)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            return [data]
        return []

    # -- low level transport -------------------------------------------
    def _raw(
        self,
        method: str,
        url: str,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        hdrs = {"Content-Type": "application/json", "User-Agent": _USER_AGENT}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=payload, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # pragma: no cover - network
            detail = exc.read().decode("utf-8", "replace") if exc.fp else ""
            raise TossInvestAPIError(
                f"{method} {url} -> HTTP {exc.code}: {detail}".strip()
            ) from None
        except urllib.error.URLError as exc:  # pragma: no cover - network
            raise TossInvestAPIError(f"{method} {url} -> {exc.reason}") from None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default