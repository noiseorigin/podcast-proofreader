# Podcast Proofreader

**简体中文** | [English](README_EN.md)

把播客 ASR 转写稿变成两套可交付结果：

1. **剪辑校对稿**：带时间戳、疑点编号和建议写法，剪辑师只需按编号回复。
2. **最终检索资料**：最终文字稿、结构化时间轴和 JSONL 检索切片。

这是一个可直接安装给 Agent 的 Skill。机械处理由内置脚本完成，语义判断由
Agent 完成，存疑内容必须交给人确认。

## 适用场景

### 1. 给剪辑师校对

Agent 读取转写稿和节目大纲，完成确定性纠错与全文复核，输出：

```text
03_review_draft/ep001/ep001.editor-review.md
```

每条疑点都包含编号、时间戳、说话人、原文、建议和原因。剪辑师可以直接回复：

```text
Q001 接受
Q002 保留
Q003 改为：正确写法
Q004 删除
```

### 2. 生成最终文字稿和时间轴

所有疑点确认后，Agent 输出：

```text
04_final_text/ep001/ep001.final.md
04_final_text/ep001/ep001.timeline.json
05_agent_chunks/ep001/ep001.chunks.jsonl
```

- `final.md`：带章节和时间戳的最终文字稿。
- `timeline.json`：章节起止时间、发言人和段落数量。
- `chunks.jsonl`：按章节和长度切分，带节目、章节、时间范围和发言人元数据，
  可直接用于全文检索、向量化或 RAG 入库。

## 安装

### 推荐：通用 Agent Skills 安装器

安装器会自动识别电脑上的 Agent：

```bash
npx skills add noiseorigin/podcast-proofreader --global --copy
```

OpenClaw 和 Hermes 可显式指定：

```bash
npx skills add noiseorigin/podcast-proofreader \
  --global \
  --agent openclaw \
  --agent hermes-agent \
  --copy \
  --yes
```

保留 `--copy`，避免部分 Agent 无法发现目录软链。

### 手动安装

也可以把整个仓库导入 Agent 的 Skill 管理器，或复制到其 Skills 目录。根目录
至少保留：

```text
SKILL.md
agents/openai.yaml
scripts/podcast_proofreader.py
references/
template/
```

例如 Codex 本地安装目录可使用
`~/.codex/skills/podcast-proofreader/`；其他 Agent 使用其 Skill 导入入口。

安装后可直接对 Agent 说：

```text
使用 podcast-proofreader，把这期转写稿和大纲整理成剪辑校对稿。
```

推荐流程只需要 Python 3.10+。DOCX 使用内置解析，不需要安装
`python-docx`。安装后先检查环境：

```bash
python3 scripts/podcast_proofreader.py doctor
```

## 适用的 Agent

本工具不绑定特定模型。只要 Agent 能读取本地文件、执行 Python 命令、写入项目
目录，并能把疑点交给人确认，就可以使用完整流程。

| Agent | 接入方式 | 支持情况 |
|---|---|---|
| OpenAI Codex | 安装整个 Skill；已提供 `agents/openai.yaml` | 开箱即用 |
| Claude Code | 安装器自动识别，或指定 `--agent claude-code` | 直接支持 |
| OpenClaw / Hermes | 使用安装器显式指定 Agent | 原生元数据 |
| Cursor / Windsurf | 安装器自动识别，也可显式指定 Agent | 直接支持 |
| Cline / Roo Code | 安装器自动识别，也可显式指定 Agent | 直接支持 |
| OpenCode / Gemini CLI / Pi | 安装器自动识别，也可显式指定 Agent | 直接支持 |
| WorkBuddy 等其他本地 Agent | 能导入 `SKILL.md` 并执行本地命令时使用 | 条件适配 |

纯聊天型 Agent 如果不能读取本地文件、运行 Python 或保存流程状态，不能独立
完成全流程；仍可辅助判断疑点，机械步骤需由用户手动运行。

## 使用前准备

最少准备一份可读取、内容非空的转写稿即可开始。为避免中途返工，建议开工前
确认以下事项：

### 必须确认

- 已安装本 Skill，并且 `doctor` 检查通过。
- 转写稿属于本期节目，文件没有损坏；支持格式见下方“输入”。
- 有明确的期号，例如 `ep001`。未指定时可由 Agent 根据文件名拟定。
- 已确定一个可写入的项目目录，用于保存中间稿、人工确认记录和最终交付。

### 建议一起提供

| 材料 | 准备建议 | 用途 |
|---|---|---|
| 原始音频 | 与转写稿为同一期、同一版本 | 让剪辑师按时间戳回听疑点 |
| 节目大纲 | 包含标题、简介、时间轴和术语线索 | 提高章节划分和专有名词识别准确度 |
| 发言人名单 | 标明“发言人1”等标签对应的真实姓名 | 减少发言人待确认项 |
| 已确认术语 | 只列确定无歧义的固定写法 | 自动修正常见错听，不误改语境词 |
| 节目总时长 | 使用 `HH:MM:SS` | 补全最后一章的准确结束时间 |
| 最终确认人 | 主播、制作人或熟悉内容的剪辑师 | 回答人名、术语和语义疑点 |

音频、转写稿和大纲应来自同一期、同一版次；若录音或剪辑后重新导出过，
请优先使用最新的一组文件。

缺少可选材料不会阻止流程，但会有以下影响：

| 缺少内容 | 影响 |
|---|---|
| 大纲 | 标题默认取文件名，章节默认为“全文” |
| 音频 | 仍可生成校对稿，但疑点需另找音源回听 |
| 发言人映射 | “发言人1”等标签会进入待确认清单 |
| 节目总时长 | 最后一章结束时间记为未知 |
| 确定性纠错 | 不做固定替换，Agent 仍会完成全文语义复核 |

`agent-review.json` 和 `answers.json` 不需要提前准备：前者由 Agent 在全文复核后
生成，后者由 Agent 根据剪辑师的明确回复生成。

## 输入

| 输入 | 必需 | 支持格式 | 作用 |
|---|---:|---|---|
| 转写稿 | 是 | `.docx` `.txt` `.md` `.srt` `.vtt` | 提供正文、说话人和时间戳 |
| 节目大纲 | 否 | Markdown | 提供标题、简介、章节和术语线索 |
| 音频 | 否 | 任意本地音频文件 | 记录路径，方便剪辑师回听 |
| 发言人映射 | 否 | JSON | 将“发言人1”映射为真实姓名 |
| 确定性纠错 | 否 | JSON | 应用无需回听即可确认的固定替换 |
| 节目时长 | 否 | `HH:MM:SS` | 确定最后一章结束时间；用于检索时建议提供 |

推荐转写格式：

```text
发言人1  00:00
欢迎收听本期节目。

发言人2  00:08
大家好，我是嘉宾。
```

也支持：

```text
00:00 发言人1：欢迎收听本期节目。
00:08 发言人2：大家好，我是嘉宾。
```

大纲参考：[template/sample_outline.md](template/sample_outline.md)。

发言人映射：

```json
{
  "发言人1": "主播甲",
  "Speaker 2": "嘉宾乙"
}
```

确定性纠错只放无歧义规则：

```json
[
  {
    "from": "回蓝天",
    "to": "回南天",
    "note": "固定同音纠错"
  }
]
```

语境不确定的词不要放入自动纠错，由 Agent 加入疑点清单。

## Agent 工作流

```text
init
  ↓
prepare：导入、解析大纲、确定性纠错、生成结构化初校
  ↓
agent-review：Agent 全文语义复核
  ↓
editor-review.md：交给剪辑师确认
  ↓
resolve：登记剪辑师回复，可分多轮
  ↓
finalize：最终文字稿 + 时间轴 + 检索切片
```

状态门禁保证：

- Agent 没有完成全文复核时，不能登记剪辑师答复。
- 仍有待确认疑点时，不能生成最终稿。
- 重复运行不会静默覆盖已有配置或不同输入。

完整命令和 JSON 契约见 [SKILL.md](SKILL.md) 与
[references/contracts.md](references/contracts.md)。

## 手动运行

通常让 Agent 自动执行即可。需要手动操作时：

```bash
# 1. 初始化项目
python3 scripts/podcast_proofreader.py init \
  --project ~/my-podcast

# 2. 准备初校
python3 scripts/podcast_proofreader.py prepare \
  --project ~/my-podcast \
  --input ~/my-podcast/00_inbox/episode-001.docx \
  --outline ~/my-podcast/outlines/ep001.md \
  --audio ~/my-podcast/audio/ep001.mp3 \
  --ep-id ep001 \
  --duration 01:12:30

# 3. 查看状态
python3 scripts/podcast_proofreader.py status \
  --project ~/my-podcast \
  --ep-id ep001
```

`agent-review` 与 `resolve` 所需 JSON 通常由 Agent 根据全文和剪辑师回复生成，
用户不需要手写。

旧版 `scripts/import_docx.py`、`scripts/build_review.py` 和 `init_project.sh`
继续保留，供已有自动化兼容使用；新项目建议使用统一脚本。旧版 DOCX 导入脚本
仍需要 `python-docx`。

## 输出目录

```text
my-podcast/
├── 00_inbox/                         # 待处理转写稿
├── 01_raw_docx/ep001/                # 原文件归档；目录名为历史兼容
├── 02_normalized_text/ep001/
│   └── ep001.raw.txt                 # 提取后的原始文字
├── 03_review_draft/ep001/
│   ├── ep001.review.json             # Agent 结构化初校输入
│   ├── ep001.questions.json          # 疑点与确认状态
│   └── ep001.editor-review.md        # 给剪辑师
├── 04_final_text/ep001/
│   ├── ep001.final.md                # 最终文字稿
│   └── ep001.timeline.json           # 结构化时间轴
├── 05_agent_chunks/ep001/
│   └── ep001.chunks.jsonl            # 检索/RAG 切片
├── manifests/ep001.json              # 单一流程状态
├── speaker_map.json
└── corrections.json
```

## 可运行示例

`examples/demo/` 提供完整的最小输入：

- `transcript.txt`
- `outline.md`
- `speaker_map.json`
- `corrections.json`
- `agent_review.json`
- `answers.json`

自动测试覆盖初始化、解析、Agent 复核、人工确认、状态门禁以及三类最终输出：

```bash
python3 -m unittest discover -s tests -v
```

## 设计原则

- 原始转写稿只归档，不原地修改。
- 确定修改与人工疑点分开记录，保留审计路径。
- 不把口语擅自润色成文章，不凭常识改写事实。
- 最终稿只使用已确认结果。
- 输出使用稳定 `schema_version`，便于后续检索系统读取。

## 隐私建议

播客文字稿可能包含未发布内容和个人信息。使用云端 Agent 前，请确认你接受
对应服务的数据政策；敏感节目建议在受控环境中处理。

## License

[MIT](LICENSE)
