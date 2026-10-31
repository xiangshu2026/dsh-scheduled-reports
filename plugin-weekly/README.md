# DSH 插件周报

每周从 **GitHub / B站** 抓最近 7 天新出的 DeepSeek Harness（DSH）相关插件，
本地过滤 + 模型打分，每条只给「一句功能简介 + 链接」，不下载任何东西。

这是 `dsh-scheduled-reports` 的一个子系统，也可以单独跑。

## 安装

```bat
pip install python-docx
```

其余全部走标准库，不装 requests / bs4 / openai。

## 跑一次

```bat
cd plugin-weekly
python run_weekly.py
```

报告默认输出到 `~/Desktop/DSH-Reports/<日期>/DSH插件周报-<日期>.docx`
（`~` 会展开成当前用户主目录）。想换位置改 `config.json` 的 `report.dir`，
或用 `--out`。

项目内 `reports/` 保留一份 md + json 备份。

## 两个来源怎么抓的

| 来源 | 方式 | 是否需要配置 |
|---|---|---|
| GitHub | 官方 Search API，搜 dsh-plugin 相关 topic/关键词，近 7 天有更新或新建的仓库；README 走 raw 域名抓 | **不用配置**（匿名额度已够用） |
| B站 | 公开搜索接口，按发布时间排序，近 7 天；自动获取 buvid3 匿名 Cookie 抗风控 | **不用配置** |

### 额度怎么控制的

GitHub 匿名额度很小（核心 60 次/小时、搜索 10 次/分钟），程序做了三件事：

1. **只发 3 次搜索**：三个查询各一次，`per_page=100` 一次拿满；
2. **README 全走 raw.githubusercontent.com**：不占 API 额度；
3. **搜索之间等 6.5 秒**：避开每分钟 10 次的搜索限速。

一次完整运行约消耗 3 次搜索 + 0 次核心额度，连续跑也不会耗尽。
想要更高额度，在 `config.json` 的 `github.token` 填一个 PAT（5000 次/小时）。

### 抖音（默认关闭）

抖音网页搜索接口**强制登录**（不登录返回 `2483 请先登录`），且新版 Edge/Chrome
有双重保护：Edge 127+ 用 App-Bound 加密（Cookie 库离线解不开），Edge 136+ 对
默认 profile 禁用远程调试端口。实测多条绕过路径全部失败，
所以 `douyin.enabled` 默认 `false`，报告里不会出现抖音段落。

想启用：自己登录抖音后用 F12 手动复制 Cookie 填进 `douyin.cookie`，
把 `enabled` 改成 `true`，再跑 `python tools\check_cookie.py douyin` 验证。

## 怎么做到「只留有用的」

1. **本地过滤**：必须和 DSH 生态强相关；命中破解、引流、机场、博彩等屏蔽词的直接扔。
2. **来源配额**：每个来源各留 14 条进模型，防止 GitHub 把名额占满。
3. **模型复核**：DeepSeek 逐条打分（0-10），低于 5 分不进报告，
   同时生成「35 字以内功能简介」和分类。
4. **历史去重**：`_cache/state.json` 记住报过的条目，30 天内不重复。

## 命令行参数

```bat
python run_weekly.py --days 14          # 放宽到 14 天
python run_weekly.py --no-llm           # 不调模型，用关键词摘要（省钱/离线）
python run_weekly.py --source github    # 只跑某个来源，可重复
python run_weekly.py --dry-run          # 不更新去重状态
python run_weekly.py --out D:\reports   # 换个输出目录
```

## 常见问题

**Q：GitHub 那栏总是空的 / 日志里有 `rate limit exceeded`？**
A：程序已经把请求压到「一次跑只用 3 次搜索」，匿名额度足够。真遇到额度耗尽
（比如短时间内手动跑了很多次），等 1 小时自动恢复；想彻底避免就填 `github.token`。

**Q：B站提示 `HTTP 412`？**
A：风控。程序会自动冷却重试并降级，不中断。要彻底缓解：浏览器登录 B站 →
F12 复制 Cookie → 填 `config.json` 的 `bilibili.cookie`。

**Q：为什么报告里某个来源显示「本周期未采集」？**
A：这是如实标注，不是 bug。抖音没配 Cookie、GitHub 额度耗尽、B站全被风控，
都会这么写，避免把「没采到」误读成「没有新插件」。

**Q：想省钱 / 没网也能跑？**
A：`python run_weekly.py --no-llm`，用关键词摘要代替模型复核，完全不调 API。

**Q：想加「小红书」「知乎」之类的来源？**
A：在 `dpw/collectors/` 下新建一个 `xxx.py`，实现
`collect(cfg, client, seen_urls, status_out) -> List[Item]`，
再在 `run_weekly.py` 的 `collectors` 列表里注册即可。

## 已知边界

- **抖音**：搜索接口需登录，自动提取不一定成功，失败会打印手动步骤，不会假装成功。
- **B站**：短时间高频搜索会触发 412 风控，程序会自动冷却并降级。
- **GitHub**：不填 token 时限速 60 次/小时、搜索 10 次/分钟。
- 模型复核会消耗 DeepSeek API tokens，`--no-llm` 可完全离线。

## 许可

MIT
