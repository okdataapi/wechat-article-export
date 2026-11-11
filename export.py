#!/usr/bin/env python3
"""公众号历史文章导出：把一个微信公众号发过的文章存成 Markdown 文件和一张 CSV 索引。

不用扫码、不用公众号后台、不用 Cookie。数据来自 okdata（https://okdata.online）的公开接口，按次付费。
Python 3.9+，只用标准库。Key 放在环境变量 OKDATA_API_KEY。

    python3 export.py --account gh_363b924965e9 --pages 3
    python3 export.py --name 36氪 --dry-run

Export a WeChat Official Account's articles to Markdown files and a CSV index. No QR login, no cookies.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import http.client
import json
import os
import re
import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

VERSION = "0.1.0"
SOURCE = "gh-wechat-article-export"
SIGN_UP = f"https://okdata.online/zh/signup/?src={SOURCE}"
API = os.environ.get("OKDATA_BASE_URL", "https://api.okdata.online").rstrip("/")
# Fallback prices (USD) if the free catalog cannot be read; the live catalog wins.
PRICES = {
    "wechat_mp.accounts.search": Decimal("0.58"),  # charged per account returned; this is the per-call cap
    "wechat_mp.accounts.articles.list": Decimal("0.04"),
    "wechat_mp.articles.get": Decimal("0.02"),
}
ARTICLES_PER_PAGE = 10
RETRY_STATUSES = {429, 500, 502, 503, 504}


class ApiError(Exception):
    def __init__(self, code: str, message: str, *, charged: Optional[bool] = False, retry: str = "no",
                 retry_after: Optional[float] = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code, self.charged, self.retry, self.retry_after = code, charged, retry, retry_after


class Okdata:
    """The few okdata calls this script needs, with safe retries and a hard spending cap."""

    def __init__(self, key: Optional[str], budget: Optional[Decimal] = None, sleep: Callable[[float], None] = time.sleep) -> None:
        self.key = key
        self.budget = budget
        self.sleep = sleep
        self.spent = Decimal("0")
        self.caps = dict(PRICES)

    def _get(self, path: str, params: Dict[str, Any], idempotency_key: Optional[str]) -> Dict[str, Any]:
        query = urlencode({k: v for k, v in params.items() if v is not None})
        headers = {"Accept": "application/json", "User-Agent": f"{SOURCE}/{VERSION}"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return request_json(f"{API}{path}?{query}", headers, self.sleep)

    def call(self, endpoint: str, **params: Any) -> Dict[str, Any]:
        cap = self.caps.get(endpoint, Decimal("0"))
        if self.budget is not None and self.spent + cap > self.budget:
            raise ApiError("budget_reached", f"下一次调用最多 ${cap}，会超过预算 ${self.budget}（已花 ${self.spent}）", retry="no")
        body = self._get("/v1/" + endpoint.replace(".", "/"), params, str(uuid.uuid4()))
        self.spent += Decimal(body.get("meta", {}).get("billing", {}).get("amount", "0"))
        return body

    def prices(self) -> Dict[str, Decimal]:
        """Current prices from the free catalog (no key, no charge); the built-in table if it cannot be read."""
        try:
            data = self._get("/v1/catalog", {}, None)["data"]
            live = {e["id"]: Decimal(e["maxCharge"]) for e in data["endpoints"]}
            self.caps = {k: live.get(k, v) for k, v in PRICES.items()}
        except (ApiError, KeyError, TypeError, ValueError, ArithmeticError):
            self.caps = dict(PRICES)
        return self.caps


def _http_error(exc: HTTPError) -> ApiError:
    try:
        body = json.loads(exc.read().decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        body = None
    if isinstance(body, dict) and "code" in body:
        return ApiError(str(body["code"]), str(body.get("message")), charged=body.get("charged", False),
                        retry=str(body.get("retry", "no")), retry_after=body.get("retry_after_seconds"))
    return ApiError(f"http_{exc.code}", str(exc.reason), charged=None,
                    retry="yes" if exc.code in RETRY_STATUSES else "no")


def request_json(url: str, headers: Dict[str, str], sleep: Callable[[float], None] = time.sleep) -> Dict[str, Any]:
    """GET with up to 2 retries on the same Idempotency-Key, so a retry is never charged twice. After a lost
    answer the call may still be running on the server: wait for it, and if we give up, say the charge is unknown."""
    retries, waits, ambiguous = 0, 0, False
    while True:
        try:
            with urlopen(Request(url, headers=headers), timeout=90) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if isinstance(body, dict) and body.get("code") == "ok":
                return body
            err = (ApiError(str(body.get("code")), str(body.get("message"))) if isinstance(body, dict)
                   else ApiError("bad_response", "unexpected answer", charged=None, retry="same_key"))
        except HTTPError as exc:
            err = _http_error(exc)
        except (OSError, ValueError, http.client.HTTPException) as exc:  # network, timeout, cut-off or non-JSON body
            err = ApiError("connection_error", str(exc), charged=None, retry="same_key")
        ambiguous = ambiguous or err.charged is None
        if ambiguous and err.code == "rate_limited" and waits < 5:
            waits += 1
            sleep(_wait(err.retry_after, 1.0))
            continue
        if err.retry not in ("yes", "same_key") or retries == 2:
            if ambiguous and err.charged is False:
                err.charged = None  # an earlier attempt may still finish and be billed
            raise err
        sleep(_wait(err.retry_after, 2.0 ** retries))
        retries += 1


def _wait(value: Any, default: float) -> float:
    """Seconds to sleep: the server's hint if it is a sane number, capped at 30."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(seconds, 0.0), 30.0)


def use_utf8() -> None:
    """Chinese text in and out, also on Windows consoles and pipes."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace" if stream is sys.stderr else "strict")


def cell(value: Any) -> Any:
    """Text that starts like a spreadsheet formula gets a leading ' so Excel shows it instead of running it."""
    return "'" + value if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


# --- export -------------------------------------------------------------------------------------

def slug(text: str, limit: int = 60) -> str:
    """A file-name-safe version of a title; keeps Chinese characters."""
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", text).strip().strip(".")
    cleaned = re.sub(r"\s+", "-", cleaned)
    return cleaned[:limit] or "untitled"


def article_path(out: Path, post: Dict[str, Any]) -> Path:
    """export/<account>/2026-11-05-<title>-<6 hex>.md; the hash keeps same-day, same-title articles apart."""
    found = re.match(r"\d{4}-\d{2}-\d{2}", str(post.get("published_at") or ""))
    day = found.group(0) if found else "undated"
    tag = hashlib.sha1(str(post.get("url") or post.get("id") or "").encode("utf-8")).hexdigest()[:6]
    title = str(post.get("title") or post.get("text") or "")[:30]
    return out / f"{day}-{slug(title)}-{tag}.md"


def to_markdown(post: Dict[str, Any], full_text: Optional[str]) -> str:
    title = post.get("title") or "(无标题)"
    meta = {
        "title": title,
        "url": post.get("url"),
        "published_at": post.get("published_at"),
        "account": (post.get("author") or {}).get("name"),
        "source": "WeChat Official Account via okdata",
    }
    head = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in meta.items())
    body = full_text if full_text is not None else (post.get("text") or "") + "\n\n（只有摘要；用 --full 取全文）"
    return f"---\n{head}\n---\n\n# {title}\n\n{body.strip()}\n"


def list_articles(ok: Okdata, account: str, pages: int) -> Iterator[Dict[str, Any]]:
    cursor = None
    for _ in range(pages):
        body = ok.call("wechat_mp.accounts.articles.list", id=account, cursor=cursor, view="compact")
        yield from body["data"]["items"]
        cursor = (body.get("page") or {}).get("next_cursor")
        if not cursor:
            return


def find_account(ok: Okdata, name: str, pick: int) -> str:
    items = ok.call("wechat_mp.accounts.search", query=name, view="compact")["data"]["items"]
    if not items:
        raise SystemExit(f"没有找到叫「{name}」的公众号。")
    for i, acc in enumerate(items, 1):
        print(f"  {i}. {acc.get('name')}  {acc.get('id')}  {acc.get('bio') or ''}"[:120], file=sys.stderr)
    if not 1 <= pick <= len(items):
        raise SystemExit(f"--pick 要在 1 到 {len(items)} 之间。")
    chosen = items[pick - 1]
    print(f"用第 {pick} 个：{chosen.get('name')}（{chosen.get('id')}）。下次直接用 --account {chosen.get('id')}，省掉搜索费。", file=sys.stderr)
    return str(chosen["id"])


def write_index(out: Path, rows: List[Dict[str, Any]]) -> None:
    fields = ["published_at", "title", "url", "likes", "views", "file"]
    with (out / "index.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: cell(v) for k, v in row.items()} for row in rows)


def charge_note(err: ApiError) -> str:
    return "不扣费" if err.charged is False else "是否扣费未知：上一次请求可能还在处理"


def plan_cost(prices: Dict[str, Decimal], *, search: bool, pages: int, full: bool) -> Decimal:
    cost = prices["wechat_mp.accounts.articles.list"] * pages
    if search:
        cost += prices["wechat_mp.accounts.search"]
    if full:
        cost += prices["wechat_mp.articles.get"] * pages * ARTICLES_PER_PAGE
    return cost


def run(args: argparse.Namespace, ok: Okdata) -> int:
    prices = ok.prices()
    most = plan_cost(prices, search=bool(args.name), pages=args.pages, full=args.full)
    print(f"计划：{'搜索公众号 1 次 + ' if args.name else ''}文章列表最多 {args.pages} 页"
          f"{f' + 全文最多 {args.pages * ARTICLES_PER_PAGE} 篇' if args.full else ''}，最多花 ${most}。"
          "已经存过全文的文章不会再取。", file=sys.stderr)
    if args.dry_run:
        return 0
    if most > args.budget:
        print(f"超过预算 ${args.budget}。用 --budget {most} 放行，或减少 --pages。", file=sys.stderr)
        return 3
    if not ok.key:
        print(f"缺少 OKDATA_API_KEY。先在 {SIGN_UP} 注册拿 key，然后 export OKDATA_API_KEY=okd_...", file=sys.stderr)
        return 2

    account = find_account(ok, args.name, args.pick) if args.name else args.account
    out = Path(args.out or f"export/{slug(account)}")
    out.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    for post in list_articles(ok, account, args.pages):
        path = article_path(out, post)
        if path.exists() and "（只有摘要" not in path.read_text(encoding="utf-8"):
            print(f"跳过（已存在）：{path.name}", file=sys.stderr)
        else:
            full_text = None
            if args.full and post.get("url"):
                try:
                    full_text = ok.call("wechat_mp.articles.get", url=post["url"])["data"]["item"].get("text")
                except ApiError as err:
                    if err.code in ("unauthorized", "insufficient_balance", "budget_reached"):
                        raise
                    print(f"全文没取到（{err.code}，{charge_note(err)}）：{post.get('title')}", file=sys.stderr)
            path.write_text(to_markdown(post, full_text), encoding="utf-8")
            print(f"已保存：{path.name}", file=sys.stderr)
        metrics = post.get("metrics") or {}
        rows.append({"published_at": post.get("published_at"), "title": post.get("title"), "url": post.get("url"),
                     "likes": metrics.get("likes"), "views": metrics.get("views"), "file": path.name})
    write_index(out, rows)
    print(f"完成：{len(rows)} 篇，索引在 {out / 'index.csv'}。实际花费 ${ok.spent}。", file=sys.stderr)
    return 0


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="把公众号历史文章导出成 Markdown 和 CSV（数据来自 okdata，按次付费）。")
    who = p.add_mutually_exclusive_group(required=True)
    who.add_argument("--account", help="公众号原始 ID（gh_ 开头）或微信号")
    who.add_argument("--name", help="公众号名称；会先搜索一次（按返回个数计费，最多 $0.58）")
    p.add_argument("--pick", type=int, default=1, help="用 --name 搜到多个时，选第几个（默认 1）")
    p.add_argument("--pages", type=int, default=3, help="文章列表取几页，每页约 10 篇（默认 3）")
    p.add_argument("--full", action=argparse.BooleanOptionalAction, default=True, help="是否取全文（默认取）")
    p.add_argument("--out", help="输出目录（默认 export/<公众号>）")
    p.add_argument("--budget", type=Decimal, default=Decimal("1"), help="最多花多少美元，超过就不跑（默认 1）")
    p.add_argument("--dry-run", action="store_true", help="只算钱，不调用")
    args = p.parse_args(argv)
    if args.pages < 1:
        p.error("--pages 至少是 1")
    return args


def main(argv: Optional[List[str]] = None) -> int:
    use_utf8()
    args = parse_args(argv)
    ok = Okdata(os.environ.get("OKDATA_API_KEY", "").strip() or None, budget=args.budget)
    try:
        return run(args, ok)
    except ApiError as err:
        hint = {"unauthorized": f"key 不对或已失效，到 {SIGN_UP} 重新拿一个。",
                "insufficient_balance": "余额不够，充值后再跑；这次没有扣费。",
                "not_found": "找不到这个公众号或文章，检查 ID。",
                "budget_reached": "已按 --budget 停下；已保存的文章下次不会重复取。"}.get(err.code, "")
        print(f"出错：{err}（{charge_note(err)}）{hint}", file=sys.stderr)
        print(f"到目前为止花费 ${ok.spent}。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
