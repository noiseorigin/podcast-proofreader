---
name: podcast-proofreader
description: 将播客 ASR 转写稿整理为结构化初校、语义疑点、剪辑校对稿和最终文字稿。用户要求导入或校对播客文稿、根据大纲纠错、识别发言人、生成疑点清单、登记人工确认、生成时间轴或知识库切片时使用；支持 DOCX、TXT、Markdown、SRT、VTT。
license: MIT
metadata:
  version: "1.1.0"
  author: noiseorigin
  homepage: https://github.com/noiseorigin/podcast-proofreader
  compatibility: Python 3.10+；推荐流程不需要第三方 Python 依赖
  user-invocable: true
  openclaw:
    emoji: "🎙️"
    homepage: https://github.com/noiseorigin/podcast-proofreader
  hermes:
    tags:
      - Podcast
      - ASR
      - Proofreading
---

# Podcast Proofreader

先确定本 `SKILL.md` 所在目录并记为 `SKILL_DIR`。所有内置脚本都从
`SKILL_DIR` 解析，不假设当前目录就是 Skill 目录。项目目录可以位于任意位置。

需要字段、JSON 示例或状态定义时，先读
[`references/contracts.md`](references/contracts.md)。

## 开工前检查

首次运行先执行：

```bash
python3 "$SKILL_DIR/scripts/podcast_proofreader.py" doctor
```

开始处理前确认：

- 转写稿存在、非空且格式受支持。
- 期号明确；用户未提供但文件名含义明确时，可使用不带扩展名的文件名。
- 项目目录可写；尚未初始化时先执行 `init`。
- 音频、转写稿和大纲属于同一期、同一版本。
- 发言人映射和确定性纠错只包含已经确认的内容。

转写稿缺失或无法读取时停止并请用户补充。其他可选材料缺失时可以继续，但要
告知影响：无大纲时使用文件名和“全文”章节；无音频时不能直接回听；无发言人
映射时生成身份疑点；无总时长时最后一章结束时间未知。不要要求用户预先编写
`agent-review.json` 或 `answers.json`。

## 工作流

严格按以下顺序执行：

```text
init → prepare → agent-review → resolve → finalize
```

### 1. 初始化

```bash
python3 "$SKILL_DIR/scripts/podcast_proofreader.py" init \
  --project "<项目目录>"
```

初始化可安全重复执行，不覆盖已有配置。建议把转写稿放入项目的
`00_inbox/`；按需填写 `speaker_map.json`、`corrections.json` 和大纲。

### 2. 准备初校

显式传入期号，避免从文件名误判：

```bash
python3 "$SKILL_DIR/scripts/podcast_proofreader.py" prepare \
  --project "<项目目录>" \
  --input "<转写稿>" \
  --ep-id "<期号>" \
  --outline "<大纲.md>" \
  --audio "<音频文件>"
```

`--outline`、`--audio`、`--title`、`--duration` 均可省略。默认读取项目根目录
的 `speaker_map.json` 和 `corrections.json`。不要自行改写生成的 JSON。

### 3. 完成 Agent 语义复核

读取以下两个文件并复核全文：

- `03_review_draft/<期号>/<期号>.review.json`
- `03_review_draft/<期号>/<期号>.questions.json`

同时读取项目 `glossary/` 中已有术语表，并按需参考
[`references/asr_patterns.md`](references/asr_patterns.md)。

只产生两类判断：

- `edits`：上下文充分、无需人工回听的确定修改。
- `questions`：人名、术语、乱码、语义或合规等仍需人工确认的内容。

已有自动疑点不要重复添加，也不要用 `edits` 改动其目标原文。保留口语原意，
不把文稿改写成文章；保护、合规或事实风险一律进入 `questions`。即使没有
新增项，也必须提交空数组，以登记复核已完成。

将结果保存为 JSON 后执行：

```bash
python3 "$SKILL_DIR/scripts/podcast_proofreader.py" agent-review \
  --project "<项目目录>" \
  --ep-id "<期号>" \
  --input "<agent-review.json>"
```

每次 `prepare` 后只执行一次 `agent-review`。成功后，把生成的
`<期号>.editor-review.md` 交给用户或剪辑师。

### 4. 登记人工确认

仅根据用户明确回复生成 answers JSON；不要代替用户猜测。允许分批登记：

```bash
python3 "$SKILL_DIR/scripts/podcast_proofreader.py" resolve \
  --project "<项目目录>" \
  --ep-id "<期号>" \
  --answers "<answers.json>"
```

若仍有待确认项，继续收集答案并重复 `resolve`。

### 5. 生成最终交付

仅在状态为 `ready_to_finalize` 时执行：

```bash
python3 "$SKILL_DIR/scripts/podcast_proofreader.py" finalize \
  --project "<项目目录>" \
  --ep-id "<期号>"
```

生成最终 Markdown、结构化时间轴和 JSONL 检索切片。

## 操作规则

- 随时用
  `python3 "$SKILL_DIR/scripts/podcast_proofreader.py" status --project "<项目目录>"`
  查看状态；排障时加 `--ep-id` 或 `--json`。
- 环境异常时先运行
  `python3 "$SKILL_DIR/scripts/podcast_proofreader.py" doctor`。
- 不直接编辑 `review.json`、`questions.json` 或 manifest；通过命令更新。
- 不覆盖原始转写稿。`--force` 会重建已有结果，除非用户明确要求，否则不用。
- 命令失败时先修正其指出的输入或契约问题，不跳过状态门禁。
