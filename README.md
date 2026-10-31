# DSH 定时报告

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
