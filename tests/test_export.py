"""Runs export.py against a local mock of the okdata API. No network, no real key."""
from __future__ import annotations

import csv
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
os.environ["NO_PROXY"] = "*"  # keep requests on this machine even with a system proxy

import export  # noqa: E402
from mock_okdata import TEST_KEY, MockOkdata, error, ok  # noqa: E402

PRICES = {"wechat_mp.accounts.search": "0.58", "wechat_mp.accounts.articles.list": "0.04", "wechat_mp.articles.get": "0.02"}


def article(i: int) -> dict:
    return {"id": f"a{i}", "url": f"https://mp.weixin.qq.com/s/a{i}", "type": "article", "title": f"第{i}篇：测试/标题",
            "text": f"摘要{i}", "published_at": f"2026-11-0{i}T08:00:00Z", "author": {"id": "gh_x", "name": "测试号"},
            "metrics": {"likes": i, "views": 100 * i}}


class ExportTest(unittest.TestCase):
    def setUp(self) -> None:
        pages = {None: ok("list", items=[article(1), article(2)], next_cursor="p2", amount="0.04"),
                 "p2": ok("list", items=[article(3)], amount="0.04")}
        self.api = MockOkdata({
            "/v1/wechat_mp/accounts/articles/list": lambda q: (200, pages[q.get("cursor")]),
            "/v1/wechat_mp/articles/get": lambda q: (404, error("not_found")) if q["url"].endswith("a3")
            else (200, ok("get", item={"text": f"全文 {q['url']}"}, amount="0.02")),
            "/v1/wechat_mp/accounts/search": lambda q: (200, ok("search", items=[{"id": "gh_x", "name": "测试号"}], amount="0.058")),
        }, prices=PRICES)
        export.API = self.api.url
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "out"

    def tearDown(self) -> None:
        self.api.close()
        self.tmp.cleanup()

    def run_export(self, *argv: str, key: str = TEST_KEY) -> tuple[int, str]:
        os.environ["OKDATA_API_KEY"] = key
        err = io.StringIO()
        with redirect_stderr(err):
            code = export.main(list(argv))
        return code, err.getvalue()

    def test_exports_markdown_and_index(self) -> None:
        code, log = self.run_export("--account", "gh_x", "--pages", "3", "--out", str(self.out))
        self.assertEqual(code, 0, log)
        files = sorted(p.name for p in self.out.glob("*.md"))
        self.assertEqual(len(files), 3)
        first = (self.out / files[0]).read_text(encoding="utf-8")
        self.assertIn("全文 https://mp.weixin.qq.com/s/a1", first)
        self.assertNotIn("/", files[0])  # the slash in the title did not become a folder
        with (self.out / "index.csv").open(encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual([r["likes"] for r in rows], ["1", "2", "3"])
        self.assertIn("全文没取到（not_found", log)  # a failed article is reported, not fatal
        self.assertIn("实际花费 $0.12", log)  # 2 list pages + 2 articles
        paid = self.api.paid()
        self.assertTrue(all(r["headers"]["authorization"] == f"Bearer {TEST_KEY}" for r in paid))
        self.assertEqual(len({r["headers"]["idempotency-key"] for r in paid}), len(paid))

    def test_second_run_skips_saved_articles(self) -> None:
        self.run_export("--account", "gh_x", "--out", str(self.out))
        before = len([r for r in self.api.paid() if r["path"].endswith("/articles/get")])
        code, log = self.run_export("--account", "gh_x", "--out", str(self.out))
        after = len([r for r in self.api.paid() if r["path"].endswith("/articles/get")])
        self.assertEqual(code, 0)
        self.assertEqual(after - before, 1)  # only the one whose full text failed last time
        self.assertIn("跳过（已存在）", log)

    def test_dry_run_prints_cost_and_calls_nothing_paid(self) -> None:
        code, log = self.run_export("--name", "测试号", "--pages", "2", "--dry-run", key="")
        self.assertEqual(code, 0)
        self.assertIn("最多花 $1.06", log)  # 0.58 search + 2 x 0.04 + 20 x 0.02
        self.assertEqual(self.api.paid(), [])

    def test_budget_blocks_big_runs(self) -> None:
        code, log = self.run_export("--account", "gh_x", "--pages", "10", "--budget", "0.5", "--out", str(self.out))
        self.assertEqual(code, 3)
        self.assertIn("超过预算", log)
        self.assertEqual(self.api.paid(), [])

    def test_missing_key_points_to_sign_up(self) -> None:
        code, log = self.run_export("--account", "gh_x", "--out", str(self.out), key="")
        self.assertEqual(code, 2)
        self.assertIn("src=gh-wechat-article-export", log)

    def test_search_by_name(self) -> None:
        code, log = self.run_export("--name", "测试号", "--pages", "1", "--no-full", "--out", str(self.out), "--budget", "2")
        self.assertEqual(code, 0, log)
        self.assertIn("--account gh_x", log)
        self.assertEqual(self.api.paid()[0]["query"]["query"], "测试号")

    def test_wrong_key_is_explained(self) -> None:
        code, log = self.run_export("--account", "gh_x", "--out", str(self.out), key="okd_wrong")
        self.assertEqual(code, 1)
        self.assertIn("unauthorized", log)
        self.assertIn("不扣费", log)


class HostileDataTest(unittest.TestCase):
    """Titles, dates and balances the script must not trust."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "out"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def serve(self, items: list, get=None) -> MockOkdata:
        api = MockOkdata({
            "/v1/wechat_mp/accounts/articles/list": lambda q: (200, ok("list", items=items, amount="0.04")),
            "/v1/wechat_mp/articles/get": get or (lambda q: (200, ok("get", item={"text": "全文"}, amount="0.02"))),
        }, prices=PRICES)
        export.API = api.url
        self.addCleanup(api.close)
        return api

    def run_export(self, *argv: str) -> tuple:
        os.environ["OKDATA_API_KEY"] = TEST_KEY
        err = io.StringIO()
        with redirect_stderr(err):
            code = export.main(["--account", "gh_x", "--out", str(self.out), *argv])
        return code, err.getvalue()

    def test_dates_cannot_escape_the_output_folder(self) -> None:
        self.serve([{**article(1), "published_at": "../../escape"}, {**article(2), "published_at": 20261101}])
        code, log = self.run_export("--pages", "1")
        self.assertEqual(code, 0, log)
        written = sorted(p.name for p in self.out.iterdir())
        self.assertEqual(len([n for n in written if n.startswith("undated-")]), 2)
        self.assertFalse((Path(self.tmp.name) / "escape").exists())

    def test_same_day_same_title_do_not_collide(self) -> None:
        twin = {**article(1), "url": "https://mp.weixin.qq.com/s/other"}
        self.serve([article(1), twin])
        self.run_export("--pages", "1")
        self.assertEqual(len(list(self.out.glob("*.md"))), 2)

    def test_formula_like_titles_are_neutralised_in_the_index(self) -> None:
        self.serve([{**article(1), "title": "=HYPERLINK(\"http://x\")"}])
        self.run_export("--pages", "1")
        with (self.out / "index.csv").open(encoding="utf-8-sig") as f:
            self.assertTrue(next(csv.DictReader(f))["title"].startswith("'="))

    def test_empty_balance_stops_instead_of_writing_summaries(self) -> None:
        api = self.serve([article(1), article(2), article(3)], get=lambda q: (402, error("insufficient_balance", retry="after_fix")))
        code, log = self.run_export("--pages", "1")
        self.assertEqual(code, 1)
        self.assertIn("余额不够", log)
        self.assertEqual(len([r for r in api.paid() if r["path"].endswith("/articles/get")]), 1)


class SlugTest(unittest.TestCase):
    def test_slug_keeps_chinese_and_drops_path_characters(self) -> None:
        self.assertEqual(export.slug('a/b:c*?"<>| 中文 标题'), "a-b-c-中文-标题")
        self.assertEqual(export.slug("..."), "untitled")


if __name__ == "__main__":
    unittest.main()
