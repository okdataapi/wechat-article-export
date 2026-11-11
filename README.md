# wechat-article-export：公众号历史文章导出 Markdown / CSV

把一个微信公众号发过的文章批量存成 Markdown 文件，再附一张 CSV 索引（标题、发布时间、链接、点赞、阅读）。
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
├── index.csv                              # 每篇一行：发布时间、标题、链接、点赞、阅读、文件名
├── 2026-11-05-标题一.md                    # 开头是 YAML 信息（标题、链接、发布时间、公众号），下面是全文
└── 2026-11-04-标题二.md
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--account` / `--name` | 二选一。知道 gh_ ID 就用 `--account`，省掉搜索费 |
| `--pages N` | 文章列表取几页，每页约 10 篇，默认 3 |
| `--no-full` | 只要标题、摘要和数据，不取全文（便宜很多） |
| `--budget 1` | 这次最多花多少美元，算出来超过就不跑，默认 $1 |
| `--dry-run` | 只算钱，不调用，不需要 key |
| `--out DIR` | 输出目录 |

重复运行是安全的：已经存过全文的文章会跳过，不会再花钱。

## 花多少钱

按 okdata 的价目表（以 [prices.json](https://github.com/okdataapi/okdata/blob/main/docs/prices.json) 为准，脚本运行时会读最新价格）：

| 操作 | 价格 |
|---|---|
| 文章列表，每页约 10 篇 | $0.04 / 页 |
| 一篇文章的全文 | $0.02 / 篇 |
| 按名字搜公众号（只有用 `--name` 时） | 每个结果 $0.058，一次最多 $0.58 |

例：`--pages 3` 导出约 30 篇带全文，最多 3 × 0.04 + 30 × 0.02 = **$0.72**。调用失败不扣钱，脚本开跑前会先打印最多花多少。

## 说明

- 这是 [okdata](https://okdata.online/zh/) 的示例工具，不是微信或腾讯的官方项目。脚本只调用 okdata 的接口，本身没有爬虫。
  用到的接口：[公众号历史文章](https://okdata.online/zh/apis/wechat_mp/accounts/articles/list/)、
  [文章详情](https://okdata.online/zh/apis/wechat_mp/articles/get/)、[公众号搜索](https://okdata.online/zh/apis/wechat_mp/accounts/search/)。
- 只导出公开发布的文章。请遵守原作者的版权，导出内容用于个人研究和归档，不要整篇转载。
- 想在 AI 里直接用（Claude Code、Cursor 等），可以接 okdata 的远程 MCP：`https://api.okdata.online/mcp`，
  或者装 [okdataapi/skills](https://github.com/okdataapi/skills)。
- 测试：`python3 -m unittest discover -s tests`（用本地模拟服务器，不联网、不花钱）。
- 问题和建议请提 issue。MIT 许可证。

---

## English

Export a WeChat Official Account's articles to Markdown files plus a CSV index, by account name or `gh_` ID.
No QR login, no admin access, no cookies. One Python 3.9+ file, standard library only. It prints the most a run
can cost before calling anything, refuses runs over `--budget` (default $1), and skips articles already saved.
List pages cost $0.04 (about 10 articles), full text $0.02 per article; failed calls are free.

Needs an okdata key in `OKDATA_API_KEY`: [sign up](https://okdata.online/signup/?src=gh-wechat-article-export).

```bash
python3 export.py --account gh_363b924965e9 --pages 3
```

Unofficial; public articles only, for personal research and archiving. MIT licence.
