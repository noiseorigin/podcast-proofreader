# Agent Operating Guide

本项目是播客文字稿校对工作区。Agent 进入本目录后按本文件执行。

## 目标

用自然语言推进播客文字稿校对工作：

- "把 inbox 里的 vol42 导入"
- "根据大纲校对 ep042"
- "列出 ep042 的疑点清单"
- "确认这些疑点，继续生成终稿"

## 工具路径

- 导入脚本: `../podcast-proofreader/scripts/import_docx.py`
- 校对脚本: `../podcast-proofreader/scripts/build_review.py`
- ASR 错听参考: `../podcast-proofreader/references/asr_patterns.md`
- 纠错示例: `../podcast-proofreader/examples/corrections.json`

## 自然语言意图映射

### 导入

用户说"导入"/"整理"时：

1. 将 docx 从 `00_inbox/` 复制到 `01_raw_docx/epXXX/`
2. 运行 `import_docx.py` 提取文本到 `02_normalized_text/epXXX/epXXX.raw.txt`
3. 创建 `manifests/epXXX.json`

### 校对

用户说"根据大纲校对"/"生成初校稿"时：

1. 读取 `02_normalized_text/epXXX/epXXX.raw.txt`
2. 读取大纲（`outlines/` 或飞书文档）
3. 识别发言人，准备纠错规则和章节定义
4. 运行 `build_review.py` 生成 `03_review_draft/epXXX/epXXX.review.md`
5. 扫描全文，追加疑点清单
6. 更新 manifest: `ai_review_draft = true`

### 疑点处理

用户说"疑点清单在哪"/"这些疑点我确认了"时：

1. 从初校稿抽取 `## 疑点清单`
2. 如用户提供确认结果，写入 `glossary/epXXX_confirmed_terms.md`
3. 用确认结果更新初校稿

### 终稿

用户说"继续生成终稿"/"完成 epXXX"时：

1. 读取人工确认后的初校稿
2. 生成 `04_final_text/epXXX/epXXX.final.md`
3. 更新 manifest: `human_final_review = true`

## 关键规则

- **不覆盖原始文件**：原始 docx 和 raw.txt 只读
- **发言人识别**：扫描前 5 分钟自我介绍，不确定时询问用户
- **ASR 纠错**：高置信度直接替换，低置信度标注 `[⚠️?]`
- **保育内容**：涉及野生保护、盗采、保护等级的内容不改写、不增强
- **术语累积**：确认的术语写入 `glossary/`，跨期复用
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

## 完成标准

一集节目完成需同时满足：

- `04_final_text/epXXX/epXXX.final.md` 存在
- 疑点已处理或明确保留
- `manifests/epXXX.json` 中 `human_final_review = true`
