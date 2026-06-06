# hk-stock-research OpenClaw 使用手册

这份文档给初学者使用。照着做，可以把 `hk-stock-research` 安装到 OpenClaw，并在飞书或 OpenClaw 里查询港股资讯、创建定时任务。

## 1. 准备条件

需要一台已经安装 OpenClaw 的机器，并能进入命令行。

检查 OpenClaw 是否可用：

```bash
openclaw health
```

检查 Python 是否可用：

```bash
python3 --version
```

脚本需要 Python 3.8 或更高版本。推荐 Python 3.10 或 3.11。

## 2. 安装 Skill

OpenClaw 推荐把 skill 放在 `~/.openclaw/skills`。

```bash
mkdir -p ~/.openclaw/skills
git clone https://github.com/wangzhaocheng-wzc/hk-stock-research.git ~/.openclaw/skills/hk-stock-research
python3 -m pip install --user -r ~/.openclaw/skills/hk-stock-research/requirements.txt
```

如果机器默认 `python3` 太旧，可以换成：

```bash
python3.11 -m pip install --user -r ~/.openclaw/skills/hk-stock-research/requirements.txt
```

如果已经安装过，更新用：

```bash
cd ~/.openclaw/skills/hk-stock-research
git pull --ff-only
python3 -m pip install --user -r requirements.txt
```

## 3. 检查安装是否成功

先直接跑一只股票：

```bash
~/.openclaw/skills/hk-stock-research/scripts/hk_research 00700
```

能看到 Markdown 报告，就说明脚本可用。

再检查 OpenClaw 是否识别到 skill：

```bash
openclaw skills list --eligible
```

列表里能看到 `hk-stock-research`，就说明 OpenClaw 可以调用。

## 4. 命令行使用

查询单只股票：

```bash
~/.openclaw/skills/hk-stock-research/scripts/hk_research 00700
```

查询多只股票：

```bash
~/.openclaw/skills/hk-stock-research/scripts/hk_research 00700 03690 09988
```

把报告保存到目录：

```bash
~/.openclaw/skills/hk-stock-research/scripts/hk_research \
  --symbols 00700,03690,09988 \
  --output-dir ~/.openclaw/reports/hk-stock/$(date +%Y-%m-%d)
```

要求行情必须是今天：

```bash
~/.openclaw/skills/hk-stock-research/scripts/hk_research 00700 --require-today
```

## 5. 在 OpenClaw 或飞书里怎么说

最简单的单只股票：

```text
使用 hk-stock-research 查询 00700 的港股资讯。
```

更完整一点：

```text
使用 hk-stock-research 查询 00700 的港股资讯，输出简洁报告。报告包含行情、估值、最新新闻、港交所公告、南向资金/持仓；保留数据日期和来源链接，拿不到的数据写 N/A，不要编造。
```

查询多只股票：

```text
使用 hk-stock-research 查询 00700、03690、09988 的港股资讯，分别生成摘要。
```

如果想要更适合飞书阅读：

```text
使用 hk-stock-research 查询 00700，按飞书消息格式输出：核心快照、走势与交易、估值与财务、最新新闻、港交所公告、南向资金/持仓、一句话总结。
```

## 6. 创建股票池

先创建一个股票池文件：

```bash
mkdir -p ~/.openclaw/data/hk-stock-research
nano ~/.openclaw/data/hk-stock-research/watchlist.txt
```

填入：

```text
00700 # 腾讯控股
03690 # 美团
09988 # 阿里巴巴
01810 # 小米集团
01024 # 快手
```

保存后测试：

```bash
~/.openclaw/skills/hk-stock-research/scripts/hk_research \
  --watchlist-file ~/.openclaw/data/hk-stock-research/watchlist.txt \
  --output-dir ~/.openclaw/reports/hk-stock/$(date +%Y-%m-%d)
```

## 7. 一句话创建定时任务

在飞书或 OpenClaw 里直接说：

```text
创建一个工作日每天上午 10 点的定时任务：使用 hk-stock-research 查询 00700、03690、09988，生成港股资讯摘要并发回当前飞书会话。报告包含行情、估值、最新新闻、港交所公告、南向资金/持仓；保留数据日期和来源链接，拿不到的数据写 N/A，不要编造。
```

如果要用股票池文件：

```text
创建一个工作日每天上午 10 点的定时任务：使用 hk-stock-research 读取 ~/.openclaw/data/hk-stock-research/watchlist.txt，生成港股资讯报告并发回当前飞书会话。报告包含行情、估值、最新新闻、港交所公告、南向资金/持仓；保留数据日期和来源链接，拿不到的数据写 N/A，不要编造。
```

## 8. 用命令创建定时任务

如果自然语言创建失败，可以直接用命令创建。

工作日每天上午 10 点执行，并把结果发回最近的聊天会话：

```bash
openclaw cron add \
  --name hk-stock-daily \
  --cron "0 10 * * 1-5" \
  --tz Asia/Shanghai \
  --message "使用 hk-stock-research 查询 00700、03690、09988，生成港股资讯摘要。报告包含行情、估值、最新新闻、港交所公告、南向资金/持仓；保留数据日期和来源链接，拿不到的数据写 N/A，不要编造。" \
  --announce \
  --timeout-seconds 600
```

使用股票池文件：

```bash
openclaw cron add \
  --name hk-stock-watchlist-daily \
  --cron "0 10 * * 1-5" \
  --tz Asia/Shanghai \
  --message "使用 hk-stock-research 读取 ~/.openclaw/data/hk-stock-research/watchlist.txt，生成港股资讯报告。报告包含行情、估值、最新新闻、港交所公告、南向资金/持仓；保留数据日期和来源链接，拿不到的数据写 N/A，不要编造。" \
  --announce \
  --timeout-seconds 600
```

说明：

- `--cron "0 10 * * 1-5"` 表示周一到周五每天 10:00。
- `--tz Asia/Shanghai` 表示使用北京时间。
- `--announce` 表示任务完成后把结果发回聊天会话。
- `--timeout-seconds 600` 表示最多等 10 分钟，避免批量报告太慢时提前超时。

## 9. 查看和测试定时任务

查看任务：

```bash
openclaw cron list
```

如果需要 JSON 输出：

```bash
openclaw cron list --json
```

创建后建议立刻测试一次。先从 `openclaw cron list` 里找到任务 id，然后运行：

```bash
openclaw cron run <任务id> --expect-final --timeout 900000
```

删除任务：

```bash
openclaw cron rm <任务id>
```

## 10. 常见问题

### 看不到 hk-stock-research

先确认目录是否存在：

```bash
ls ~/.openclaw/skills/hk-stock-research/SKILL.md
```

再看 OpenClaw 是否识别：

```bash
openclaw skills list --eligible
```

### 提示缺 Python 包

重新安装依赖：

```bash
python3 -m pip install --user -r ~/.openclaw/skills/hk-stock-research/requirements.txt
```

### 飞书没有返回完整报告

把指令说具体一点：

```text
使用 hk-stock-research 查询 00700，必须输出完整报告，包含行情、估值、新闻、港交所公告、南向资金/持仓和一句话总结；不要只输出一句话。
```

### 定时任务创建失败

用命令创建，避免模型把参数写错：

```bash
openclaw cron add \
  --name hk-stock-daily \
  --cron "0 10 * * 1-5" \
  --tz Asia/Shanghai \
  --message "使用 hk-stock-research 查询 00700、03690、09988，生成港股资讯摘要并发回当前飞书会话。" \
  --announce \
  --timeout-seconds 600
```

### 数据为 N/A

这是正常保护。免费公开数据源可能失败、限流或当天没有更新。报告会保留数据日期和错误提示，不会编造数据。

## 11. 推荐给 OpenClaw 的固定指令

可以把下面这段作为日常固定指令：

```text
当我询问港股代码或要求港股日报时，优先使用 hk-stock-research。输出时保留数据日期、来源链接和失败提示；报告至少包含行情、估值、新闻、港交所公告、南向资金/持仓和一句话总结；拿不到的数据写 N/A，不要编造，不要给个性化投资建议。
```
