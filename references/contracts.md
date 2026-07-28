# Podcast Proofreader 契约

本文定义 `scripts/podcast_proofreader.py` 的输入、输出、Agent 复核、人工答复
和状态机。命令通过 `SKILL_DIR/scripts/podcast_proofreader.py` 调用，项目目录
可以位于任意位置。

## 目录

- [输入契约](#输入契约)
- [文件输出](#文件输出)
- [Agent 的两类输出](#agent-的两类输出)
- [agent-review JSON](#agent-review-json)
- [answers JSON](#answers-json)
- [状态机](#状态机)

## 输入契约

### 项目与期号

- `--project`：项目工作目录；先用 `init` 创建。
- `--ep-id`：1–64 个字符，以字母或数字开头，只能包含字母、数字、点、
  下划线和连字符。建议始终显式传入。
- 同一期号使用相同输入重复 `prepare` 是幂等操作；输入散列不同会拒绝覆盖，
  只有明确重建时才使用 `--force`。重建会保留旧原稿版本，并把已有最终交付
  移入同目录的 `archive/`。

### 转写稿

`--input` 必填，支持：

- `.docx`
- `.txt`
- `.md`
- `.srt`
- `.vtt`

DOCX 直接读取段落和表格；文本编码支持 UTF-8、UTF-8 BOM 和 GB18030。
SRT/VTT 使用字幕起止时间，正文形如 `姓名：内容` 时识别姓名，否则记为
`未标注`。

普通文本推荐使用以下任一结构：

```text
发言人1  00:00
第一段内容。

发言人2  00:08
第二段内容。
```

```text
00:00 发言人1：第一段内容。
00:08 发言人2：第二段内容。
```

时间戳可用 `MM:SS`、`HH:MM:SS`，也可带毫秒。没有可识别的发言人和时间戳
时，全文仍会作为一个 `未标注`、从 `00:00:00` 开始的 block。

### 大纲

`--outline` 可选，使用 Markdown。解析约定：

```markdown
# 节目标题

## 节目信息
- 主播：甲、乙
- 嘉宾：丙

## 节目介绍
一段节目简介。

## 时间轴
- 00:00 开场
- 12:30 主题讨论

## 本期术语线索
| 正确写法 | 常见错听 | 备注 |
|---|---|---|
| 龟背竹 | 龟背猪 | 植物名 |
```

- H1 用作默认标题。
- H2 名称包含“节目介绍 / 节目简介 / 简介”时读取简介。
- H2 名称包含“时间轴 / 章节”时读取章节；每项必须是“时间戳 + 标题”。
- H2 名称包含“节目信息 / 嘉宾 / 主播”时读取
  `- 主播：...`、`- 嘉宾：...`。
- H2 名称包含“术语”时读取术语表。第二列可用 `、 / , ， ; ；` 分隔多个错写。
- 没有章节时自动生成从 `00:00:00` 开始的“全文”章节。

### 发言人映射

默认读取项目根目录 `speaker_map.json`，也可用 `--speaker-map` 指定：

```json
{
  "发言人1": "主播甲",
  "Speaker 2": "嘉宾乙"
}
```

键和值都必须是非空字符串。未映射且形如“发言人 N / Speaker N”的标签会成为
自动疑点。

### 确定性纠错

默认读取项目根目录 `corrections.json`，也可用 `--corrections` 指定。支持简写：

```json
[
  ["回蓝天", "回南天"]
]
```

以及带说明的写法：

```json
[
  {
    "from": "龟背猪",
    "to": "龟背竹",
    "note": "已确认的固定术语"
  }
]
```

规则会对所有 block 做一次性、非级联的精确字符串替换，只应放无歧义的确定性
规则。命中次数写入 `review.json` 的 `correction_stats`。

### 其他可选输入

- `--audio`：必须指向现有文件，仅记录路径供人工回听；不会转写、分析或复制音频。
- `--title`：覆盖大纲 H1。
- `--duration`：节目总时长，如 `01:20:30`。SRT/VTT 有末尾时间时可自动取得；
  普通转写只有段落开始时间，省略后最后一章结束时间记为未知。
- 显式总时长不得早于任何正文或章节时间。

## 文件输出

结构化文件使用以下版本标识：

| 文件 | `schema_version` |
|---|---|
| manifest | `podcast-proofreader.manifest.v1` |
| review | `podcast-proofreader.review.v1` |
| questions | `podcast-proofreader.questions.v1` |
| timeline | `podcast-proofreader.timeline.v1` |
| 每条 chunk | `podcast-proofreader.chunk.v1` |

### A. 工作与人工校对输出

`prepare` 创建：

| 文件 | 用途 |
|---|---|
| `01_raw_docx/<期号>/<原文件名>` | 原始转写稿归档；目录名为历史兼容，不限 DOCX |
| `02_normalized_text/<期号>/<期号>.raw.txt` | 提取后的原始文本 |
| `03_review_draft/<期号>/<期号>.review.json` | Agent 的结构化初校输入 |
| `03_review_draft/<期号>/<期号>.questions.json` | 自动疑点、Agent 复核状态和处理结果 |
| `03_review_draft/<期号>/<期号>.editor-review.md` | 供用户或剪辑师回听确认的可读稿 |
| `manifests/<期号>.json` | 当前状态、输入散列、输出路径和计数 |

`review.json` 中最重要的字段：

- `blocks[]`：`id`、`speaker_raw`、`speaker`、`start/end`、
  `start_seconds/end_seconds`、`text`。
- `chapters[]`：`id`、`title`、`start`、`start_seconds`。
- `term_hints[]`、`correction_stats[]`、`agent_edits[]`。
- `inputs`、`parse`、`duration`、`title`、`description`、`people`。

`questions.json` 中每个 `items[]` 包含：

- `id`：如 `Q001`，人工答复必须引用它。
- `target`：文本目标或发言人目标。
- `block_id`、`start`、`speaker`：回听定位。
- `category`、`original`、`suggestion`、`reason`、`confidence`。
- `status`：`pending` 或 `resolved`。
- `resolution`：处理前为 `null`，处理后记录动作、文本和时间。

不要直接修改这些生成文件。Agent 修改走 `agent-review`，人工确认走 `resolve`；
`editor-review.md` 会随之自动刷新。

### B. 最终交付输出

`finalize` 创建：

| 文件 | 用途 |
|---|---|
| `04_final_text/<期号>/<期号>.final.md` | 已应用全部确认结果的最终文字稿 |
| `04_final_text/<期号>/<期号>.timeline.json` | 含章节起止、block 数和发言人的结构化时间轴 |
| `05_agent_chunks/<期号>/<期号>.chunks.jsonl` | 按章节与目标字符数拆分的检索切片 |

`--chunk-chars` 默认 `1800`，不得小于 `200`。最终稿已存在时默认幂等返回；
只有明确重新生成时使用 `--force`。

`timeline.json` 包含 `episode_id`、标题、总时长及 `chapters[]`；每章记录
`id`、标题、起止秒数与格式化时间、block 数和发言人。`chunks.jsonl`
每行是一个独立 JSON 对象，包含 chunk ID、节目和章节标识、起止时间、
发言人、`block_ids`、分段后的 `turns`、字符数、源文件散列及正文。相邻长切片
会尽量保留一个短 turn 作为重叠上下文，并通过 `overlaps_previous` 标识。

## Agent 的两类输出

语义复核必须遍历 `review.json` 的全部 `blocks`，并先查看
`questions.json` 以避免重复。判断只分两类：

1. **确定修改 `edits`**
   - 上下文充分，不需要回听即可确认。
   - 只修正错字、明确术语、说话人文本中的确定错误。
   - 不润色口语，不扩写，不改变事实或语气。
2. **人工疑点 `questions`**
   - 需要听音频或由编辑判断。
   - 包括人名、外文、专名、数字、断句、乱码、语义矛盾和合规风险。
   - 给出原文、建议和理由；没有可靠建议时将 `suggestion` 留空。

保护、法律、医疗、事实陈述等高风险内容不得凭常识改写，放入 `questions`。
已有 `pending` 疑点的目标由人工处理，不再放入 `edits`，否则会使疑点引用的
原文失效。

## agent-review JSON

完整形态：

```json
{
  "edits": [
    {
      "block_id": "B00012",
      "original": "唯一命中的原文片段",
      "replacement": "确定写法",
      "reason": "大纲与上下文均能确认"
    }
  ],
  "questions": [
    {
      "target_type": "text",
      "block_id": "B00018",
      "category": "人名",
      "original": "原文中的唯一片段",
      "suggestion": "可能的正确写法",
      "reason": "同音人名，需回听",
      "confidence": "low"
    },
    {
      "target_type": "speaker",
      "original": "发言人3",
      "suggestion": "嘉宾乙",
      "reason": "根据自我介绍推测，需确认",
      "confidence": "medium"
    }
  ],
  "notes": "已复核全部 block。"
}
```

约束：

- `edits`、`questions` 必须为数组；无内容时使用 `[]`。
- `edits[].block_id` 必须存在。
- `edits[].original` 和 `replacement` 必须是字符串；`original` 必须在该 block
  当前 `text` 中恰好出现一次。
- `questions[].target_type` 只能是 `text` 或 `speaker`，省略时为 `text`。
- 文本疑点必须提供有效 `block_id`。若后续可能接受、替换或删除，
  `original` 应为 block 中唯一命中的精确片段。
- 发言人疑点的 `original` 是待替换的完整发言人标签。
- `category`、`suggestion`、`reason`、`confidence` 为说明字段；
  `confidence` 推荐 `low` 或 `medium`。
- 不要让 `edits` 与 `questions` 指向同一片段，也不要创建相互重叠的疑点，
  否则最终应用时可能无法唯一命中。
- 脚本先应用 `edits`，再登记 `questions`。疑点原文应与修改后的 block 一致。
- 每次 `prepare` 后只成功提交一次。若状态已离开 `needs_agent_review`，不要重复提交。

提交后，脚本会把确定修改写入 `review.json`，给新增疑点分配 `Qxxx`，
将 `agent_review.completed` 设为 `true`，并刷新剪辑校对稿和 manifest。

## answers JSON

推荐使用带 `answers` 的对象：

```json
{
  "answers": {
    "Q001": {
      "action": "accept"
    },
    "Q002": {
      "action": "keep"
    },
    "Q003": {
      "action": "replace",
      "text": "人工确认的写法"
    },
    "Q004": {
      "action": "remove"
    }
  }
}
```

动作：

| action | 中文别名 | 含义 | 额外要求 |
|---|---|---|---|
| `accept` | `接受` | 采用疑点的 `suggestion` | suggestion 必须非空 |
| `keep` | `保留` | 保留原文 | 无 |
| `replace` | `改为` | 使用人工提供的文字 | `text` 必须非空 |
| `remove` | `删除` | 删除目标原文 | 无 |

发言人疑点通常只使用 `replace` 或 `keep`；`remove` 会把该发言人标签替换为空。

也支持简写：

```json
{
  "Q001": "accept",
  "Q002": {
    "action": "replace",
    "text": "正确写法"
  }
}
```

或数组：

```json
[
  {"id": "Q001", "action": "keep"},
  {"id": "Q002", "action": "replace", "text": "正确写法"}
]
```

约束：

- 只回答 `questions.json` 中存在的 ID。
- 可只提交本轮明确回答的部分；未提交项保持 `pending`。
- 不把沉默、模糊回复或 Agent 推测转换成答案。
- `accept/replace/remove` 在最终应用时要求文本目标能唯一命中；若不能唯一命中，
  应先让用户明确更长的原文范围。

## 状态机

```text
项目初始化
   │ init
   ▼
无期目记录
   │ prepare
   ▼
needs_agent_review
   │ agent-review
   ├─ 有 pending ───────────► awaiting_editor
   │                           │ resolve（可多轮）
   │                           └─ pending = 0
   └─ 无 pending ───────────► ready_to_finalize
                               │ finalize
                               ▼
                            finalized
```

| 状态 | 含义 | 允许的下一步 |
|---|---|---|
| `needs_agent_review` | 机械准备完成，尚未登记 Agent 全文复核 | `agent-review` |
| `awaiting_editor` | Agent 已复核，仍有人工疑点 | `resolve` |
| `ready_to_finalize` | Agent 已复核，所有疑点已处理 | `finalize` |
| `finalized` | 最终稿、时间轴和切片已生成 | 查看交付；明确需要时重新生成 |

门禁：

- Agent 未复核时，`resolve` 和 `finalize` 都会拒绝执行。
- 仍有 `pending` 疑点时，`finalize` 会拒绝执行。
- `resolve` 支持多轮，全部处理后自动进入 `ready_to_finalize`。
- `render` 仅刷新 `editor-review.md`，不改变判断或绕过门禁。
- 使用 `status --project "<项目目录>" --ep-id "<期号>"` 查看单期状态，
  使用 `status ... --json` 获取结构化状态。
