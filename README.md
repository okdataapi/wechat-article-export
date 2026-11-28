# wechat-article-export：公众号历史文章导出 Markdown / CSV

[English](#english): export WeChat Official Account articles to Markdown and CSV from anywhere, no login.

把一个微信公众号发过的文章批量存成 Markdown 文件，再附一张 CSV 索引（标题、发布时间、链接；加 `--metrics` 还有阅读、点赞、在看、分享）。
**不用扫码登录，不用公众号后台，不用抓包或 Cookie。**一个 Python 文件，只用标准库，Python 3.9 以上就能跑。

适合：做竞品公众号的内容归档、把喜欢的号整理成知识库、喂给 AI 做总结或检索。

## 用法

先在 [okdata](https://okdata.online/zh/signup/?src=gh-wechat-article-export) 注册拿一个 key，然后：

```bash
git clone https://github.com/okdataapi/wechat-article-export
cd wechat-article-export
export OKDATA_API_KEY=okd_...        # 不要写进代码或提交到仓库

python3 export.py --account gh_363b924965e9 --pages 3   # 用原始 ID（gh_ 开头）或微信号
python3 export.py --name 36氪 --dry-run                 # 只知道名字：先看要花多少钱
python3 export.py --name 36氪 --pages 2                 # 搜到多个时用 --pick 2 选第二个
```

导出结果：

```
export/gh_363b924965e9/
├── index.csv                              # 每篇一行：发布时间、标题、链接、阅读、点赞、在看、分享、文件名
├── 2026-11-05-标题一.md                    # 开头是 YAML 信息（标题、链接、发布时间、公众号），下面是全文
└── 2026-11-04-标题二.md
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--account` / `--name` | 二选一。知道 gh_ ID 就用 `--account`，省掉搜索费 |
| `--pages N` | 文章列表取几页，每页约 10 篇，默认 3 |
| `--no-full` | 只要标题和摘要，不取全文（便宜很多） |
| `--metrics` | 再取每篇的阅读、点赞、在看、分享，每篇多一次调用。文章列表本身一般不带这些数，不加这个参数时 CSV 里这几列是空的 |
| `--budget 1` | 这次最多花多少美元，算出来超过就不跑，默认 $1 |
| `--dry-run` | 只算钱，不调用，不需要 key |
| `--out DIR` | 输出目录 |

重复运行是安全的：已经存过全文的文章会跳过，不会再花钱。一页的篇数不固定（大号一页可能有 20 篇），中途因为 `--budget` 或余额停下时，已经取到的阅读数也会写进 index.csv。

## 花多少钱

按 okdata 的价目表（以 [prices.json](https://github.com/okdataapi/okdata/blob/main/docs/prices.json) 为准，脚本运行时会读最新价格）：

| 操作 | 价格 |
|---|---|
| 文章列表，每页约 10 篇 | $0.02 / 页 |
| 一篇文章的全文 | $0.02 / 篇 |
| 一篇文章的阅读、点赞、在看、分享（`--metrics`） | $0.02 / 篇 |
| 按名字搜公众号（只有用 `--name` 时） | 每个结果 $0.058，一次最多 $0.58 |

例：`--pages 3` 导出约 30 篇带全文，最多 3 × 0.02 + 30 × 0.02 = **$0.66**；再加 `--metrics` 是 **$1.26**。脚本开跑前会先打印最多花多少。

## 说明

- 这是 [okdata](https://okdata.online/zh/?src=gh-wechat-article-export) 的示例工具，不是微信或腾讯的官方项目。脚本只调用 okdata 的接口，本身没有爬虫。
  用到的接口：[公众号历史文章](https://okdata.online/zh/apis/wechat_mp/accounts/articles/list/?src=gh-wechat-article-export)、
  [文章详情](https://okdata.online/zh/apis/wechat_mp/articles/get/?src=gh-wechat-article-export)、[文章阅读数](https://okdata.online/zh/apis/wechat_mp/articles/metrics/?src=gh-wechat-article-export)、[公众号搜索](https://okdata.online/zh/apis/wechat_mp/accounts/search/?src=gh-wechat-article-export)。
- 只导出公开发布的文章。请遵守原作者的版权，导出内容用于个人研究和归档，不要整篇转载。
- 想在 AI 里直接用（Claude Code、Cursor 等），可以接 okdata 的远程 MCP：`https://api.okdata.online/mcp`，
  或者装 [okdataapi/skills](https://github.com/okdataapi/skills)。
- 测试：`python3 -m unittest discover -s tests`（用本地模拟服务器，不联网、不花钱）。
- 问题和建议请提 issue。MIT 许可证。

---

## English

Export a WeChat Official Account (公众号) to Markdown files plus a CSV index: every article's full text, title,
publish time and link, and optionally its reads, likes, recommends and shares. No QR login, no admin access to the
account, no cookies, no Chinese phone number. One Python 3.9+ file, standard library only.

WeChat Official Accounts are where Chinese companies, brands, media and government bodies publish first. Those
articles are hard to find from outside WeChat, so this is a way to keep a searchable copy:
a competitor's announcements, a regulator's notices, an industry newsletter, or a corpus for an AI to summarise.

### Run it

Get a key at [okdata.online](https://okdata.online/signup/?src=gh-wechat-article-export) (pay per call, no
subscription), then:

```bash
git clone https://github.com/okdataapi/wechat-article-export
cd wechat-article-export
export OKDATA_API_KEY=okd_...        # keep it out of code and commits

python3 export.py --account gh_363b924965e9 --pages 3   # by original ID (starts with gh_) or WeChat ID
python3 export.py --name 36氪 --dry-run                 # only know the name: see what it costs first
python3 export.py --name 36氪 --pages 2                 # several matches? --pick 2 takes the second
```

The output is one folder per account:

```
export/gh_363b924965e9/
├── index.csv                     # one row per article: published, title, link, reads, likes, recommends, shares, file
├── 2026-11-05-<title>.md         # YAML front matter (title, link, published, account), then the full text
└── 2026-11-04-<title>.md
```

| Flag | |
|---|---|
| `--account` / `--name` | One of the two. With the original ID (starts with `gh_`) or the WeChat ID no search is needed |
| `--pages N` | Pages of the article list, about 10 articles each (default 3) |
| `--no-full` | Titles and summaries only, no full text (much cheaper) |
| `--metrics` | Also fetch reads, likes, recommends and shares, one more call per article |
| `--budget USD` | Refuse to start if the run could cost more (default $1) |
| `--dry-run` | Print the cost and stop; needs no key |

Running it again is safe: articles already saved with full text are skipped and cost nothing.

### What it costs

The article list is $0.02 per page of about 10 articles, full text $0.02 per article, metrics $0.02 per article,
and a search by name $0.058 per result (at most $0.58). `--pages 3` with full text, about 30 articles, is at most
3 × 0.02 + 30 × 0.02 = **$0.66**; with `--metrics` **$1.26**. The script reads the current prices and prints the
most a run can cost before calling anything.

### Reading it in English

The articles are in Chinese. Point an LLM at the folder and ask for what you need, for example "summarise each
article in two English sentences and list the products and prices mentioned", or connect okdata's remote MCP
(`https://api.okdata.online/mcp`, see [okdata.online/mcp](https://okdata.online/mcp/?src=gh-wechat-article-export))
to Claude or Cursor and let the assistant fetch and translate the articles itself.

Unofficial and not affiliated with WeChat or Tencent; the script only calls the okdata API. Public articles only:
respect the authors' copyright and use the exports for research and archiving, not republishing. MIT licence.
