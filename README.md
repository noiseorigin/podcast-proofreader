# Podcast Proofreader

**简体中文** | [English](README_EN.md)

给 Podcast 创作者用的 ASR 文字稿初校 Skill。

你提供一份带发言人和时间戳的 DOCX 转写稿，再提供本期大纲；Agent 会整理发言人、应用已确认的纠错规则、插入章节，并把不确定内容集中到疑点清单，方便你只回听真正需要确认的片段。

> 当前版本优先服务中文播客，命令行流程面向 macOS/Linux，并以「先生成初校稿，再由人确认」为原则。不会在证据不足时擅自改写原话。

## 最快开始

### 1. 安装 Skill

推荐使用通用 Agent Skills 安装器。它会自动识别你电脑上的 Agent：

```bash
npx skills add noiseorigin/podcast-proofreader --global --copy
```

OpenClaw 和 Hermes 可直接指定：

```bash
npx skills add noiseorigin/podcast-proofreader \
  --global \
  --agent openclaw \
  --agent hermes-agent \
  --copy \
  --yes
```

这里保留 `--copy`，避免部分 Agent 不读取目录软链。

### 2. 安装 DOCX 依赖

```bash
python3 -m pip install python-docx
```

### 3. 让 Agent 创建工作区

安装后直接对 Agent 说：

```text
请在 ~/PodcastTranscripts 创建一个播客校对项目。
```

Agent 会调用本 Skill 的初始化脚本，创建收件箱、初校稿、终稿、大纲和术语目录。

### 4. 放入本期文件

- 把 ASR 导出的 DOCX 放进 `00_inbox/`
- 把本期大纲保存为 `outlines/ep042.outline.md`

然后说：

```text
请把 00_inbox/episode042.docx 作为 ep042 导入，
根据 outlines/ep042.outline.md 生成初校稿。
不确定的人名、术语和句子不要猜，放进疑点清单。
```

Agent 会在信息不足时先问你发言人姓名，而不是自行编造。

## 你会得到什么

```text
03_review_draft/ep042/ep042.review.md
```

初校稿包含：

- 已映射的发言人姓名
- 原始时间戳
- 章节标题
- 高置信度术语修正
- 需要人工回听的疑点清单

确认疑点后，对 Agent 说：

```text
这些疑点已经确认，请更新术语表并生成 ep042 终稿。
```

终稿保存到：

```text
04_final_text/ep042/ep042.final.md
```

## 当前支持

- 带发言人标签和时间戳的 `.docx` ASR 转写稿
- 本地 Markdown 节目大纲
- `发言人1`、`Speaker 1` 等标签的显式映射
- 精确字符串纠错规则
- 按时间戳插入章节
- Agent 语境校对与疑点清单
- 人工确认后的 Markdown 终稿

## 输入格式

转写稿需要类似下面的结构：

```text
发言人1   00:00
欢迎收听本期节目。

发言人2   00:08
大家好，很高兴来到这里。
```

支持 `MM:SS` 和 `HH:MM:SS` 时间戳。

如果 ASR 使用 `Speaker 1` 或其他标签，Agent 会通过 speaker map 映射到真实姓名。

## 工作区结构

```text
PodcastTranscripts/
├── 00_inbox/              # 新导出的 DOCX 放这里
├── 01_raw_docx/           # 原始文件归档
├── 02_normalized_text/    # 提取后的纯文本
├── 03_review_draft/       # 初校稿和疑点清单
├── 04_final_text/         # 人工确认后的终稿
├── outlines/              # 本期大纲
├── glossary/              # 人工确认的术语
├── manifests/             # 每期处理状态
├── corrections.json       # 精确纠错规则
└── chapters.json          # 章节时间戳和标题
```

原始 DOCX 和 `raw.txt` 只读保留，初校和终稿写入新的目录。

## 手动命令

大多数创作者不需要手动运行命令。下面内容用于排错或自动化。

### 初始化项目

```bash
bash /path/to/podcast-proofreader/init_project.sh ~/PodcastTranscripts
```

### 导入 DOCX

```bash
cd ~/PodcastTranscripts

python3 /path/to/podcast-proofreader/scripts/import_docx.py \
  --input 00_inbox/episode042.docx \
  --ep-id ep042 \
  --output-dir 02_normalized_text \
  --raw-dir 01_raw_docx \
  --manifest-dir manifests \
  --title "本期标题"
```

### 生成结构化初校稿

```bash
python3 /path/to/podcast-proofreader/scripts/build_review.py \
  --raw 02_normalized_text/ep042/ep042.raw.txt \
  --outline outlines/ep042.outline.md \
  --output 03_review_draft/ep042/ep042.review.md \
  --ep-id ep042 \
  --speaker-map '{"发言人1":"嘉宾","发言人2":"主播"}' \
  --corrections corrections.json \
  --chapters chapters.json \
  --title "本期标题"
```

脚本只负责可重复的机械处理。大纲比对、语境判断和疑点清单由 Agent 完成。

## 配置文件

### `corrections.json`

只放已经确认、可以直接替换的词：

```json
[
  ["Open AI", "OpenAI"],
  ["Chat G P T", "ChatGPT"]
]
```

不确定的替换不要写进这里，应放入疑点清单。

### `chapters.json`

```json
[
  ["00:00", "开场"],
  ["04:30", "嘉宾经历"],
  ["18:20", "核心讨论"]
]
```

## 校对原则

1. 高置信度、已确认的错误可以直接修正。
2. 人名、品牌名、数字、否定词和事实陈述不确定时必须保留并标记。
3. 不把口语整段改写成文章，不改变说话人的原意。
4. 每条疑点必须带时间戳，方便回听。
5. 只有用户确认后才生成终稿。

## 隐私建议

播客文字稿可能包含未发布内容和个人信息。使用云端 Agent 前，请确认你接受对应服务的数据政策；敏感节目建议在受控环境中处理。

## 开发与测试

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
```

## License

[MIT](LICENSE)
