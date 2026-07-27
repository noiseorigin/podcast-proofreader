# Podcast Proofreader

将播客 ASR 语音转写稿（通义听悟、飞书妙记、Whisper 等）快速校对为结构化、可读的初校稿。

通过节目大纲交叉比对，自动完成：发言人识别、术语纠错、章节插入、疑点标记，输出带时间戳的 Markdown 初校稿 + 疑点清单，供人工终审。

---

## 这解决什么问题

播客制作人拿到 ASR 转写稿后，通常面临：

- **发言人全是"发言人1/2/3"**，读不下去
- **专有名词大量错听**（植物名、人名、品牌名被替换成同音字）
- **没有章节结构**，2 小时的文本是一整坨
- **不知道哪些地方 ASR 听错了**，需要逐句回听

本工具通过「大纲驱动校对」解决以上问题：你提供节目大纲（飞书文档/本地文件），工具自动比照大纲内容做术语纠错和章节切分，并生成疑点清单让你只需回听不确定的部分。

## 适合谁用

- 有**节目大纲**（或 shownotes / 时间轴）的中文播客主播
- 使用**通义听悟、飞书妙记、Whisper** 等工具导出 docx/txt 转写稿
- 希望将转写稿加工为可发布、可检索的知识库内容

> 不限于中文播客——英文播客同样适用，只需调整纠错规则和发言人映射。

## 快速开始

### 方式一：WorkBuddy 用户（推荐）

1. 下载 [podcast-proofreader.zip](releases)
2. 在 WorkBuddy 中打开「设置 → Skill 管理 → 导入」
3. 选择 zip 文件，完成安装
4. 在对话中说「根据大纲校对 ep042」，Skill 自动激活

### 方式二：命令行直接使用

```bash
git clone https://github.com/your-username/podcast-proofreader.git
cd podcast-proofreader
pip install python-docx

# Step 1: 导入 docx 转写稿
python scripts/import_docx.py \
  --input ~/Downloads/episode042.docx \
  --ep-id ep042 \
  --output-dir 02_normalized_text \
  --raw-dir 01_raw_docx \
  --manifest-dir manifests

# Step 2: 准备发言人映射和纠错规则（参考 examples/ 目录）

# Step 3: 生成初校稿
python scripts/build_review.py \
  --raw 02_normalized_text/ep042/ep042.raw.txt \
  --outline outlines/ep042.outline.md \
  --output 03_review_draft/ep042/ep042.review.md \
  --ep-id ep042 \
  --speaker-map '{"发言人1": "嘉宾名", "发言人2": "主播A", "发言人3": "主播B"}' \
  --corrections examples/corrections.json \
  --chapters examples/chapters.json \
  --title "Vol.42 节目标题"
```

## 输入要求

### 必需

| 输入 | 格式 | 说明 |
|------|------|------|
| ASR 转写稿 | `.docx` 或 `.txt` | 通义听悟/飞书妙记/Whisper 导出，需包含发言人编号和时间戳 |
| 节目大纲 | 飞书文档 URL 或本地 `.md` 文件 | 包含章节标题、讨论主题、术语线索 |

### 转写稿格式要求

脚本兼容以下格式（通义听悟默认导出）：

```
发言人1   00:00
这里是转写文本内容。

发言人2   00:08
另一段转写文本。
```

> 也支持 `Speaker 1`、`说话人A` 等格式，通过 `--speaker-map` 参数映射。

### 可选

| 输入 | 格式 | 说明 |
|------|------|------|
| 纠错规则 | JSON | `[["错听词", "正确词"], ...]` 格式，参考 `examples/corrections.json` |
| 章节定义 | JSON | `[["时间戳", "章节标题"], ...]` 格式，参考 `examples/chapters.json` |
| 已确认术语表 | Markdown | 前期节目积累的术语，放在 `glossary/` 目录 |

## 输出说明

### 初校稿 (`epXXX.review.md`)

```markdown
# Vol.42 节目标题｜第一版校对稿

> 状态：AI 初校 / 术语清理版，仍需人工回听终审。

## 节目介绍
（从大纲提取）

## 时间轴
- 00:00 开场前导
- 01:21 开场与嘉宾介绍
- 03:10 第一个话题
...

## 正文

### [00:00] 开场前导

**迪哥** [00:00]：请不要跟我说...

**朱兜兜** [00:08]：得不到的永远在骚动。
...

## 疑点清单

### 1. [人名] 嘉宾社交平台名
原文"迪goa delia迪哥"，ASR可能不准确，需确认。

### 2. [植物名] 绿麦秋海棠
原文多次出现"绿麦/绿脉"混用，已统一为"绿麦"。
...
```

### Manifest (`manifests/epXXX.json`)

记录每期处理状态，支持断点续做：

```json
{
  "episode_id": "ep042",
  "status": {
    "raw_docx_copied": true,
    "text_extracted": true,
    "ai_review_draft": true,
    "human_final_review": false,
    "agent_chunks_exported": false
  }
}
```

## 项目目录结构

建议按以下结构组织你的播客文本项目：

```
my-podcast-transcripts/
├── 00_inbox/              # ASR 导出的原始文件扔这里
├── 01_raw_docx/           # 导入后自动复制到此目录
├── 02_normalized_text/    # 提取的纯文本
├── 03_review_draft/       # AI 初校稿（带疑点清单）
├── 04_final_text/         # 人工终审稿
├── 05_agent_chunks/       # 知识库切片（可选）
├── outlines/              # 节目大纲、时间轴
├── glossary/              # 已确认术语（跨期累积）
├── manifests/             # 每期处理状态 JSON
├── corrections.json       # 你的纠错规则（跨期复用）
└── chapters/              # 章节定义（跨期复用）
```

## ASR 纠错策略

纠错按置信度从高到低执行，低置信度的不自动替换，而是进入疑点清单：

| 置信度 | 类型 | 处理方式 | 示例 |
|--------|------|---------|------|
| 高 | 节目名/主播名 | 直接替换 | 猪兜兜→朱兜兜 |
| 高 | 同音词混淆 | 直接替换 | 回蓝天→回南天 |
| 中 | 语境依赖词 | 带上下文替换 | 交水→浇水（仅在浇水语境） |
| 低 | 专有名词/学名 | 标记疑点 | "bigod a rex"→可能是 Begonia rex |
| 低 | 整句乱码 | 保留原文+标记 | 无法通过替换修复 |

完整错听模式参考：[`references/asr_patterns.md`](references/asr_patterns.md)

## 自定义纠错规则

创建 `corrections.json`，定义你的播客专属纠错规则：

```json
[
  ["错听词1", "正确词1"],
  ["错听词2", "正确词2"]
]
```

规则会逐条执行简单字符串替换。对于语境依赖的纠错（如"交水"仅在浇水语境替换为"浇水"），建议在生成初校稿后由 AI agent 做上下文感知的二次修正。

参考示例：[`examples/corrections.json`](examples/corrections.json)

## 术语累积机制

每期校对完成后，将人工确认的术语写入 `glossary/epXXX_confirmed_terms.md`。后续期数自动加载已有术语表，实现跨期累积——校对越多，准确率越高。

```
glossary/
├── ep042_confirmed_terms.md   # 第42期确认的术语
├── ep043_confirmed_terms.md   # 第43期确认的术语
└── ...
```

## 飞书大纲获取

如果你的节目大纲在飞书文档中：

```bash
# 切换到对应的飞书 profile（如果是非默认 workspace）
lark-cli profile use my-profile

# 获取文档内容（Markdown 格式）
lark-cli docs +fetch --doc "https://xxx.feishu.cn/docx/XXXX" --doc-format markdown

# 切回默认 profile
lark-cli profile use default
```

> 需要 [lark-cli](https://www.npmjs.com/package/lark-cli) 已安装并完成认证。

## 常见问题

### Q: 支持 Whisper 导出的转写稿吗？

支持。Whisper 导出的 SRT/VTT 文件可以先转为 docx 或 txt（保持发言人+时间戳格式），然后使用本工具。如果是纯文本无时间戳，章节插入功能将不可用，但纠错和疑点清单仍可正常生成。

### Q: 非中文播客可以用吗？

可以。`build_review.py` 的 `--speaker-map` 和 `--corrections` 参数与语言无关。`references/asr_patterns.md` 中的错听模式以中文为主，英文播客需自行编写纠错规则。

### Q: 疑点清单是怎么生成的？

脚本完成纠错后，AI agent 会扫描全文，识别以下类型的可疑内容：
- ASR 乱码段落（语法不通、上下文断裂）
- 未在术语表中的专有名词
- 人名不一致（同一人出现多种写法）
- 保育/合规相关内容（需保守处理）

### Q: 可以批量处理多期节目吗？

可以。编写 shell 脚本循环调用 `import_docx.py` 和 `build_review.py`，配合 manifest 状态管理实现批量处理。建议每期处理后人工确认疑点再继续下一期。

### Q: 终审稿和知识库切片怎么生成？

终审稿（`04_final_text/`）在人工确认所有疑点后，由 AI agent 根据确认结果更新初校稿生成。知识库切片（`05_agent_chunks/`）将终审稿按章节+时间戳切分为 JSONL 格式，可直接导入 RAG 系统。这两个步骤需要 AI agent（如 WorkBuddy）执行，脚本仅处理初校阶段。

## 技术要求

- Python 3.10+
- `python-docx` 库（`pip install python-docx`）
- （可选）lark-cli — 用于获取飞书大纲文档

## License

MIT License — 自由使用、修改、分发。

## 贡献

欢迎提交 Issue 和 PR：
- 补充 ASR 错听模式到 `references/asr_patterns.md`
- 改进脚本性能或兼容性
- 分享你的 `corrections.json` 纠错规则
