# Podcast Transcript Proofreading — Claude Code Instructions

## 项目概述

本项目是播客文字稿校对工作区。Claude Code 在此目录中工作时应遵循以下流程。

## 工具路径

- 导入脚本: `../podcast-proofreader/scripts/import_docx.py`
- 校对脚本: `../podcast-proofreader/scripts/build_review.py`
- ASR 错听参考: `../podcast-proofreader/references/asr_patterns.md`
- 纠错示例: `../podcast-proofreader/examples/corrections.json`

## 工作流

### 1. 导入

当 00_inbox/ 中有新的 docx 文件时：

```bash
python ../podcast-proofreader/scripts/import_docx.py \
  --input 00_inbox/episode.docx \
  --ep-id epXXX \
  --output-dir 02_normalized_text \
  --raw-dir 01_raw_docx \
  --manifest-dir manifests
```

### 2. 获取大纲

如果大纲在飞书文档中，使用 lark-cli 获取：

```bash
lark-cli profile use <profile_name>
lark-cli docs +fetch --doc "<feishu_url>" --doc-format markdown > outlines/epXXX.outline.md
lark-cli profile use default
```

如果大纲是本地文件，直接读取 outlines/ 目录。

### 3. 校对

读取大纲和原始文本后：

1. 扫描前 5 分钟文本，识别发言人自我介绍，建立 `发言人N → 真实姓名` 映射
2. 参考大纲中的术语线索和 `corrections.json`，准备 ASR 纠错规则
3. 参考大纲时间轴，准备章节定义
4. 运行 build_review.py 生成初校稿

```bash
python ../podcast-proofreader/scripts/build_review.py \
  --raw 02_normalized_text/epXXX/epXXX.raw.txt \
  --outline outlines/epXXX.outline.md \
  --output 03_review_draft/epXXX/epXXX.review.md \
  --ep-id epXXX \
  --speaker-map '{"发言人1": "Name1", "发言人2": "Name2"}' \
  --corrections corrections.json \
  --chapters chapters.json \
  --title "Vol.XX 标题"
```

### 4. 生成疑点清单

脚本生成初校稿后，Claude Code 应：

1. 读取初校稿全文
2. 扫描以下类型的问题：
   - ASR 乱码段落（语法不通、上下文断裂）
   - 未在术语表中的专有名词
   - 人名不一致（同一人多种写法）
   - 保育/合规相关内容
3. 将疑点追加到初校稿末尾的 `## 疑点清单` 部分
4. 每条疑点格式：`### N. [类别] 名称` + 描述 + 时间戳

### 5. 终稿

用户确认疑点后：

1. 根据确认结果更新初校稿
2. 将确认的术语写入 `glossary/epXXX_confirmed_terms.md`
3. 生成终稿到 `04_final_text/epXXX/epXXX.final.md`
4. 更新 `manifests/epXXX.json` 中 `human_final_review = true`

## 关键规则

- **不覆盖原始文件**：原始 docx 和 raw.txt 只读
- **发言人识别**：从开场自我介绍识别，不确定时询问用户
- **ASR 纠错**：高置信度直接替换，低置信度标注 `[⚠️?]` 并列入疑点清单
- **保育内容**：涉及野生保护、盗采、保护等级的内容不改写、不增强
- **术语累积**：每期确认的术语写入 glossary/，后续期数自动参考
- **BGM 歌词**：保留原文，在疑点清单中标注

## 文件结构

```
00_inbox/              原始 docx 收件箱
01_raw_docx/           原始 docx 归档
02_normalized_text/    提取的纯文本
03_review_draft/       AI 初校稿（带疑点清单）
04_final_text/         人工终审稿
05_agent_chunks/       知识库切片（可选）
outlines/              节目大纲
glossary/              已确认术语
manifests/             每期状态 JSON
corrections.json       纠错规则
chapters.json          章节定义
```
