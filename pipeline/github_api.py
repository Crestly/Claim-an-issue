"""Minimal GitHub REST + GraphQL client. Stdlib only.

Limits handled (documented in docs/LIMITS.md):
* REST primary: 5,000 req/h per personal token (60 unauthenticated). We read
  X-RateLimit-Remaining/Reset and sleep when below a floor.
* Search: 30 req/min authenticated; we throttle to <= 28/min.
* GraphQL: 5,000 points/h; we read rateLimit{cost remaining resetAt} on every query.
* Secondary limits: on 403/429 with Retry-After we sleep that long; without it
  we back off exponentially (60s, 120s, 240s) and give up after 4 tries.
* Concurrency: this client is sequential (one request at a time), well under
  the 100-concurrent secondary limit and the 900 points/min REST limit.

The budget object lets the orchestrator stop before exhausting the token so
the next scheduled run always has headroom.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

API = "https://api.github.com"
UA = "claimanissue-pipeline/0.1 (+https://github.com/Crestly/Claim-an-issue; contact in repo README)"


@dataclass
class Budget:
    rest_used: int = 0
    graphql_used: int = 0  # points
    search_used: int = 0
    rest_remaining: int | None = None
    graphql_remaining: int | None = None
    search_remaining: int | None = None
    rest_floor: int = 300       # stop REST when fewer than this remain
    graphql_floor: int = 300    # stop GraphQL when fewer points remain
    errors: int = 0
    log: list[str] = field(default_factory=list)

    def ok_rest(self) -> bool:
        return self.rest_remaining is None or self.rest_remaining > self.rest_floor

    def ok_graphql(self) -> bool:
        return self.graphql_remaining is None or self.graphql_remaining > self.graphql_floor

    def summary(self) -> dict:
        return {"rest_used": self.rest_used, "graphql_used": self.graphql_used, "search_used": self.search_used,
                "rest_remaining": self.rest_remaining, "graphql_remaining": self.graphql_remaining, "errors": self.errors}


class RateLimited(Exception):
    pass


class GitHub:
    def __init__(self, token: str | None, budget: Budget | None = None, verbose: bool = False):
        self.token = token
        self.budget = budget or Budget()
        self.verbose = verbose
        self._search_times: list[float] = []

    # ------------------------------------------------------------------ core
    def _headers(self, extra: dict | None = None) -> dict:
        h = {"User-Agent": UA, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if extra:
            h.update(extra)
        return h

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, file=sys.stderr)

    def _request(self, method: str, url: str, body: bytes | None = None, headers: dict | None = None, tries: int = 4):
        delay = 60
        for attempt in range(tries):
            req = urllib.request.Request(url, data=body, method=method, headers=self._headers(headers))
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                    return r.status, dict(r.headers), data
            except urllib.error.HTTPError as e:
                hdrs = dict(e.headers)
                payload = e.read()
                remaining = hdrs.get("X-RateLimit-Remaining")
                retry_after = hdrs.get("Retry-After")
                if e.code in (403, 429) and (retry_after or remaining == "0"):
                    if retry_after:
                        wait = int(retry_after) + 1
                    else:
                        reset = int(hdrs.get("X-RateLimit-Reset", time.time() + 60))
                        wait = max(5, reset - int(time.time()) + 2)
                    self.budget.errors += 1
                    self._log(f"rate limited ({e.code}); would wait {wait}s")
                    # Never sit out a full hourly reset: stop this stage so the
                    # orchestrator can export whatever it already has.
                    if wait > 90:
                        raise RateLimited(f"rate limit reset is {wait}s away")
                    time.sleep(wait)
                    continue
                if e.code in (502, 503, 504) and attempt < tries - 1:
                    self.budget.errors += 1
                    time.sleep(delay)
                    delay *= 2
                    continue
                if e.code == 403 and attempt < tries - 1:  # secondary limit without headers
                    self.budget.errors += 1
                    self._log(f"403 without retry-after; backing off {delay}s")
                    time.sleep(delay)
                    delay *= 2
                    continue
                return e.code, hdrs, payload
            except (urllib.error.URLError, TimeoutError) as e:
                self.budget.errors += 1
                if attempt == tries - 1:
                    raise
                time.sleep(delay)
                delay *= 2
        raise RateLimited("gave up")

    def _track_rest(self, headers: dict) -> None:
        self.budget.rest_used += 1
        rem = headers.get("X-RateLimit-Remaining") or headers.get("x-ratelimit-remaining")
        if rem is not None:
            res = headers.get("X-RateLimit-Resource") or headers.get("x-ratelimit-resource") or "core"
            if res == "search":
                self.budget.search_remaining = int(rem)
            elif res == "core":
                self.budget.rest_remaining = int(rem)

    # ------------------------------------------------------------------ REST
    def rest(self, path: str, params: dict | None = None, accept: str | None = None):
        """GET a REST endpoint. Returns (status, json_or_None, headers)."""
        if not self.budget.ok_rest():
            raise RateLimited("REST budget floor reached")
        url = path if path.startswith("http") else API + path
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        status, headers, data = self._request("GET", url, headers={"Accept": accept} if accept else None)
        self._track_rest(headers)
        if status == 204 or not data:
            return status, None, headers
        try:
            return status, json.loads(data), headers
        except json.JSONDecodeError:
            return status, data.decode("utf-8", "replace"), headers

    def rest_paginated(self, path: str, params: dict | None = None, max_pages: int = 10):
        params = dict(params or {})
        params.setdefault("per_page", 100)
        page = 1
        while page <= max_pages:
            params["page"] = page
            status, body, headers = self.rest(path, params)
            if status != 200 or not isinstance(body, list):
                break
            yield from body
            if len(body) < params["per_page"]:
                break
            page += 1

    def search_issues(self, q: str, per_page: int = 100, page: int = 1, sort: str | None = None):
        """Search API: 30 req/min authenticated, 1,000 results per query max.
        Uses advanced_search=true (required for the new syntax; AND semantics between
        repeated repo:/org:/user: qualifiers)."""
        now = time.time()
        self._search_times = [t for t in self._search_times if now - t < 60]
        per_minute = 28 if self.token else 9  # unauthenticated search is 10/min
        if len(self._search_times) >= per_minute:
            wait = 60 - (now - self._search_times[0]) + 0.5
            self._log(f"search throttle: sleeping {wait:.1f}s")
            time.sleep(max(0, wait))
        self._search_times.append(time.time())
        params = {"q": q, "per_page": per_page, "page": page, "advanced_search": "true"}
        if sort:
            params["sort"] = sort
        status, body, headers = self.rest("/search/issues", params)
        self.budget.search_used += 1
        self.budget.rest_used -= 1  # counted separately
        return status, body

    # -------------------------------------------------------------- GraphQL
    def graphql(self, query: str, variables: dict | None = None):
        if not self.token:
            raise RateLimited("GraphQL requires a token")
        if not self.budget.ok_graphql():
            raise RateLimited("GraphQL budget floor reached")
        if "rateLimit" not in query:
            # Inject rateLimit so every response reports cost.
            query = query.rstrip()
            assert query.endswith("}"), "query must end with }"
            query = query[:-1] + " rateLimit { cost remaining resetAt } }"
        body = json.dumps({"query": query, "variables": variables or {}}).encode()
        status, headers, data = self._request("POST", API + "/graphql", body=body, headers={"Content-Type": "application/json"})
        self._track_rest(headers)
        self.budget.rest_used -= 1
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            raise RateLimited(f"GraphQL non-JSON response ({status})")
        rl = (payload.get("data") or {}).get("rateLimit")
        if rl:
            self.budget.graphql_used += int(rl.get("cost") or 0)
            self.budget.graphql_remaining = int(rl.get("remaining") or 0)
        if "errors" in payload and not payload.get("data"):
            msgs = "; ".join(e.get("message", "?") for e in payload["errors"])
            if "rate limit" in msgs.lower():
                raise RateLimited(msgs)
            raise RuntimeError(f"GraphQL error: {msgs[:300]}")
        return payload

    # ----------------------------------------------------------- utilities
    def rate_limit(self) -> dict:
        status, body, _ = self.rest("/rate_limit")
        self.budget.rest_used -= 1  # /rate_limit is free
        if isinstance(body, dict):
            res = body.get("resources", {})
            self.budget.rest_remaining = res.get("core", {}).get("remaining")
            self.budget.graphql_remaining = res.get("graphql", {}).get("remaining")
            self.budget.search_remaining = res.get("search", {}).get("remaining")
        return body if isinstance(body, dict) else {}

    def get_file(self, owner: str, repo: str, path: str, ref: str | None = None) -> str | None:
        """Raw file content or None (1 REST request). Used for CONTRIBUTING.md, .claimable.yml, etc."""
        params = {"ref": ref} if ref else None
        status, body, _ = self.rest(f"/repos/{owner}/{repo}/contents/{path}", params, accept="application/vnd.github.raw+json")
        if status == 200 and isinstance(body, str):
            return body
        if status == 200 and isinstance(body, dict) and body.get("encoding") == "base64":
            import base64
            return base64.b64decode(body["content"]).decode("utf-8", "replace")
        return None
