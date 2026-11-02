# DSH 定时报告

[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![DeepSeek Harness](https://img.shields.io/badge/DeepSeek%20Harness-plugin-purple)](https://github.com/xiangshu2026/dsh-scheduled-reports)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)](#)
[![Unattended](https://img.shields.io/badge/mode-unattended%20%2B%20catch--up-green)](#)

> 原仓库：https://github.com/xiangshu2026/dsh-scheduled-reports
> 如果你是从别处下载的，建议回原仓库获取最新版与 issue 支持。

让 **DeepSeek Harness** 每周自动给你出几份报告，转成 Word 存到桌面。无人值守，
开机自动补跑，日志可查。

四份报告：

| 报告 | 内容 | 需要联网 |
|---|---|---|
| **电脑状况报告** | 磁盘 / 内存 / CPU / 开机时长，运行时的真实快照 | 否 |
| **AI 大模型动态** | 最近 7 天 AI 领域的新消息 | 是 |
| **插件更新检查** | 已装 DSH 插件哪些有新版本 | 是（查 npm） |
| **DSH 插件周报** | 最近 7 天新出的 DSH 插件（GitHub + B站） | 是 |

> **它做什么、不做什么**
>
> 它只是「定时把 DSH 拉起来，按任务说明书生成 Markdown，再转成 Word」。
> 报告写得好不好，取决于你在 `tasks/*.md` 里怎么描述要求——那里是纯中文的
> 任务说明，用大白话写，改完下次运行就生效，不用改代码。
>
> **不采集任何个人数据**：不读聊天记录、不读浏览器、不上传任何内容。
> 电脑状况报告默认把盘符和进程名脱敏成 `disk-1` / `app-01`（见下方隐私开关）。

---

## 安装

### 需要什么

- **Windows**（批处理 + PowerShell，Linux/macOS 不适用）
- **DeepSeek Harness** 桌面版，且 `dsh` 命令可用
- **Python 3.9+** 和 `python-docx`（转 Word 用）

```bat
pip install python-docx
```

### 三步跑起来

1. **放到一个固定目录**，比如 `%USERPROFILE%\.dsh\scheduled`：
   ```bat
   git clone https://github.com/xiangshu2026/dsh-scheduled-reports.git "%USERPROFILE%\.dsh\scheduled"
   ```

2. **确认 API Key 能被读到**。headless 模式只从进程环境变量取 key，
   所以脚本会从 `%USERPROFILE%\.dsh\.credentials.yaml` 的 `refs:` 段里
   把 `DEEPSEEK_API_KEY` 取出来注入。如果你用别的方式存 key，
   直接设环境变量 `DEEPSEEK_API_KEY` 也可以。

3. **手动跑一次**，确认能出报告：
   ```bat
   run-reports-now.cmd
   ```
   会提示调用几次模型、大约几分钟，按任意键开始。

报告默认落在 `%USERPROFILE%\Desktop\DSH-Reports\<YYYY-MM-DD>\`，只放 `.docx`。

### 装成每周自动跑

```powershell
$action  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument '/c "%USERPROFILE%\.dsh\scheduled\run-daily-task.cmd"'
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9am
Register-ScheduledTask -TaskName "DSH-Scheduled-Reports" -Action $action -Trigger $trigger
```

卸载：`Unregister-ScheduledTask -TaskName "DSH-Scheduled-Reports"`

---

## 配置

### 三个开关（都在 `run-daily-task.cmd` 顶部）

| 设置 | 默认 | 说明 |
|---|---|---|
| `WORKDIR` | `%USERPROFILE%\Desktop\DSH-Reports` | 报告输出根目录，也是 agent 唯一能动的目录 |
| `DSH_PERMISSION_MODE` | `workspace-write` | agent 权限。**建议不要改**成 `danger-full-access`，无人值守时很危险 |
| `KEEPDAYS` | `180` | 报告保留天数。**别调太低**，否则新报告会把旧的删掉 |

### 跑哪些报告（`TASKLIST`）

```bat
set "TASKLIST=1-computer.md 2-ai-models.md 5-plugin-updates.md"
```

不想要的从这行删掉即可，**每少跑一个任务就少花一份钱**。联网的那两个最贵。

### 隐私开关（电脑状况报告）

`collect-system-info.ps1` 有个 `-Redact` 参数，默认 `1`：

| Redact | 效果 |
|---|---|
| `1`（默认） | 盘符 → `disk-1`/`disk-2`；进程名 → `app-01`/`app-02`；PID → `hidden`。**容量、占用率、CPU 百分比全部保留**，报告照样能看 |
| `0` | 显示真实盘符和进程名。**只在你一个人看这些报告时才用** |

---

## 四份报告各自怎么工作

### 电脑状况报告

`collect-system-info.ps1` 在 agent 沙盒**外面**用完整权限跑（agent 在沙盒里查不到
WMI/CIM，会瞎猜），把磁盘、内存、CPU、开机时长落成 `system-info.txt`，
agent 只负责读和写报告。

### AI 大模型动态

纯联网搜索，`tasks/2-ai-models.md` 里限定了搜索次数（6–9 次）和关注范围
（DeepSeek / Anthropic / OpenAI / Google 等）。想换关注点就改那个 md。

### 插件更新检查

`collect-plugin-updates.ps1` 读 DSH profile 的 `package.json`，逐个查 npm registry
比对版本。`link:` / `file:` / `github:` 来源的本地插件在 npm 上本来就查不到，
会被标成 `registry-error`——**这是正常的，不是错误**。

### DSH 插件周报

独立的一套（`plugin-weekly/`），从 GitHub Search API + B站搜索抓最近 7 天的新插件，
本地过滤 + 模型打分，输出 Markdown / JSON / docx。详见 `plugin-weekly/README.md`。

---

## 目录结构

```
dsh-scheduled-reports/
├─ run-daily-task.cmd           执行器（改配置就改这里）
├─ run-reports-now.cmd          手动跑一次
├─ tasks/                       任务说明书（纯中文，随便改）
│  ├─ 1-computer.md
│  ├─ 2-ai-models.md
│  └─ 5-plugin-updates.md
├─ collectors/                  沙盒外采集与后处理
│  ├─ collect-system-info.ps1   磁盘/内存/CPU（带隐私脱敏）
│  ├─ collect-plugin-updates.ps1 插件版本比对
│  ├─ post-process.ps1          md → docx、删源文件、清理旧报告
│  ├─ md2docx.py                Markdown 转 Word
│  ├─ get-api-key.ps1           从凭据文件取 key
│  └─ acquire-lock.ps1          单实例锁
└─ plugin-weekly/               DSH 插件周报（独立子系统）
```

---

## 健康检查哨兵（sentinel）

定时任务有个很隐蔽的失败模式：**退出码 0，但什么都没产出**。

计划任务看到 0 就当成功了，于是你以为它一直在跑，实际上已经空转好几天。

`run-sentinel.cmd` 专门查这件事——**不看任务返回值，看副作用**。

### 检查四项

| 检查项 | 判据 | 阈值 |
|---|---|---|
| 每日报告 | 日期新鲜 + 份数够 + 类别不单一 | 9 天 |
| 审计账本 | 最后同步时间 | 7 天 |
| 审计日志 | 最后写入时间 | 7 天 |
| 定时日志 | 最新日志时间 | 9 天 |

### 「份数 + 类别」是双重判据

只查「有没有文件」会误判。实测遇到过：某天目录里只有 1 份报告（插件周报），
但计划任务应该产 4 份——只查「有文件」会报 OK，加上「应该 4 份」
和「类别不能单一」才能识别出「只跑了一部分」。

### 退出码分三层

```
0 = 全绿
1 = 告警（能容忍，不影响使用）
2 = 严重（必须处理）
```

**为什么告警不返回失败**：如果 warn 也算失败，计划任务天天显示「上次运行失败」，
人会麻木，真问题反而被淹没。

### 用法

```bat
run-sentinel.cmd
```

装成每天自动跑：

```powershell
$action  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument '/c "%USERPROFILE%\.dsh\scheduled\run-sentinel.cmd"'
$trigger = New-ScheduledTaskTrigger -Daily -At 9:30am
Register-ScheduledTask -TaskName "DSH-Sentinel" -Action $action -Trigger $trigger
```

### 输出示例

```
⚠️  每日报告   最新 2026-10-26 · 1 份 · 3.8 小时前（只有 1/4 份；类别单一）
──────────────────────────────
常见原因（仅供排查，不是结论）：
  · 任务确实没跑起来 / 计划任务被禁用
  · 目录被误删或手动清理
  · 部分子任务失败，只生成了部分报告
  · 机器当天没开机
```

注意最后那段是「常见原因，不是结论」。**哨兵只报事实，不猜原因**——
猜错原因会把人引到错误的方向。

---

## DSH 工具：report_health

作为 DSH 插件装进 profile 后，本仓库注册一个工具 **`report_health`**，把上面哨兵那套「看副作用」的检查直接交给模型调用。

```js
// 模型侧看到的形态
report_health()                 // 用默认路径与阈值
report_health({ reportsDir: 'D:\\Reports', maxReportDays: 14 })  // 覆盖个别参数
```

返回结构（与 `output.schema` 严格一致）：

```json
{
  "worst": "ok",
  "ok": true,
  "items": [
    { "item": "每日报告", "level": "ok", "ok": true, "detail": "最新 2026-11-02 · 5 份 · 1.6 小时前" },
    { "item": "审计账本", "level": "ok", "ok": true, "detail": "登记 4471 行 · 最后同步 1.3 小时前" }
  ]
}
```

`worst` 三档：`ok` 全绿 / `warn` 有告警 / `error` 有严重项。

**注册方式**：`ctx.tools.register({ name, description, parameters, output, execute })`。

> ⚠️ 不要用 `ctx.tools.guard` 注册工具。`guard` 只接受一个 `ToolGuard` 函数
> `(execution) => string | undefined`，用来做单调拒绝；传字符串会被 append 进 guard 层，
> 每次工具调用执行 `guard(exec)` 时抛 TypeError，可能连累 profile 内所有工具调用。

自测：`node test/selftest.mjs`（校验注册契约、schema 自洽、render 输出，5 条断言）。

---

## 常见问题

**Q：跑起来说 `MISSING_CREDENTIAL`？**
A：headless 模式不读桌面版的凭据引用，只认进程环境变量。检查
`%USERPROFILE%\.dsh\.credentials.yaml` 里 `refs:` 段有没有 `DEEPSEEK_API_KEY`，
或者直接设环境变量。

**Q：报告没生成，怎么查？**
A：看 `logs\summary-<日期>.log` 最后一行：`RUN END: ALL OK` 是全部成功，
`SOME TASKS FAILED` 有失败。具体哪一份失败看 `logs\<日期>-<任务名>.log`，
结尾是 `exit=0` 即成功。

**Q：一次跑多久、花多少钱？**
A：三份报告约 4–5 分钟。花钱的只有联网那两份和模型调用，量级很小，
具体看你用的模型定价。

**Q：为什么 `run-daily-task.cmd` 里全是英文、一个中文都没有？**
A：**故意的**。cmd.exe 按字节位置解析批处理文件，一旦混入中文（多字节），
它会把后面的行读串位，连正常命令都被切碎，整个流程崩。中文只能写在
`tasks/*.md` 里——那是纯文本，安全。

**Q：能改成每天跑吗？**
A：能。改计划任务的触发器就行。但注意联网那两份报告是按「运行当天往前推 7 天」
算的，天天跑内容会大量重叠。

**Q：报告会不会重复？**
A：不会。每期按日期建子文件夹，`KEEPDAYS` 天之前的自动清理。

**Q：能加自己的报告吗？**
A：能。在 `tasks/` 下新建一个英文名 `.md`，用大白话写清楚要它做什么，
然后把文件名加进 `TASKLIST`。会自动跟着转 Word、跟着被清理。

---

## 已知边界

- **只支持 Windows**。批处理 + PowerShell + WMI 的组合，换平台要重写。
- **依赖 DSH 本体**。没有 DeepSeek Harness 就跑不了——这套东西本质是
  「让 DSH 定时干活」的调度壳子。
- **AI 大模型动态 / 插件周报需要联网**。断网时这两份会失败，
  电脑状况和插件检查仍能正常出。
- **模型会写错**。报告内容由模型生成，可能有不准确的地方，
  尤其是联网搜索类（日期、链接可能出错）。当参考看，别当事实源。
- **不做任何数据上传**。所有内容都留在本机。
- 本项目不含任何政治类内容生成任务。

---

## 许可

MIT
