---
name: podcast-proofreader
description: "Podcast ASR transcript proofreading skill. Transforms raw ASR exports into structured review drafts by cross-referencing show outlines, applying terminology corrections, and flagging uncertain items for human review. Works with any language and any ASR tool (Tongyi Tingwu, Feishu Miaoji, Whisper, etc.). Triggers: proofread episode, 根据大纲校对, 导入播客文本, 生成初校稿, ASR纠错."
agent_created: true
---

# Podcast Proofreader

## Overview

Transform raw ASR podcast transcripts into structured, readable review drafts by cross-referencing show outlines, applying domain-specific terminology corrections, and flagging uncertain items for human review.

Works with any ASR tool that exports docx or txt with speaker labels and timestamps (Tongyi Tingwu, Feishu Miaoji, Whisper, etc.), and any language.

## When to Use

- A podcast host provides a docx/txt ASR export and asks to proofread it
- A user says "根据大纲校对" / "proofread episode XX" / "生成初校稿"
- A user wants to import a new podcast episode transcript for processing
- A user provides a document URL (Feishu/Lark/Google Docs) as the show outline and asks to cross-reference

## Prerequisites

### Environment

- Python 3.10+ with `python-docx` installed (`pip install python-docx`)
- `lark-cli` configured (only if outlines are on Feishu/Lark)

### Directory Structure

Each podcast project should follow this structure (adaptable):

```
project-root/
├── 00_inbox/              Raw ASR exports (docx/txt) land here
├── 01_raw_docx/           Copied raw files, organized by episode
├── 02_normalized_text/    Extracted plain text
├── 03_review_draft/       AI-proofread drafts with questions
├── 04_final_text/         Human-reviewed final transcripts
├── 05_agent_chunks/       Knowledge base chunks (optional)
├── outlines/              Show outlines, timelines, terminology
├── glossary/              Confirmed terms (accumulates across episodes)
├── manifests/             Per-episode processing state (JSON)
├── imports/               SRT/VTT import intermediates
├── tools/                 Automation scripts
├── corrections.json       ASR correction rules (cross-episode)
└── chapters.json          Chapter definitions (cross-episode)
```

> **Tip**: Run `./init_project.sh /path/to/project` from the repo root to scaffold this entire structure automatically, complete with template files.

## Workflow

### Phase 1: Import

When a user provides a file in `00_inbox/` or a file path:

1. Copy the raw file to `01_raw_docx/epXXX/`.
2. Extract text to `02_normalized_text/epXXX/epXXX.raw.txt` using `scripts/import_docx.py`.
3. Create a manifest at `manifests/epXXX.json` with initial status flags.

```bash
python scripts/import_docx.py \
  --input "00_inbox/episode.docx" \
  --ep-id ep042 \
  --output-dir 02_normalized_text \
  --raw-dir 01_raw_docx \
  --manifest-dir manifests
```

### Phase 2: Fetch Outline

If the user provides a Feishu/Lark doc URL as the outline:

1. Switch to the appropriate lark-cli profile if needed.
2. Fetch the document: `lark-cli docs +fetch --doc "<URL>" --doc-format markdown`.
3. Save to `outlines/epXXX.outline.md`.
4. Switch back to the default profile.

If the outline is a local file, read it directly.

### Phase 3: ASR Correction & Review Draft Generation

This is the core phase. Use `scripts/build_review.py`:

1. **Read** the raw text and the outline.
2. **Identify speakers** by scanning the first few minutes for self-introductions. Map `发言人N` / `Speaker N` to real names.
3. **Apply corrections** based on:
   - The podcast's glossary (accumulated in `glossary/`).
   - Common ASR error patterns (see `references/asr_patterns.md`).
   - Domain-specific terminology from the outline.
4. **Insert chapter headers** by mapping outline sections to timestamps.
5. **Flag uncertain items** in a `## 疑点清单` section at the end.
6. **Write** the review draft to `03_review_draft/epXXX/epXXX.review.md`.
7. **Update** the manifest: `ai_review_draft = true`.

```bash
python scripts/build_review.py \
  --raw 02_normalized_text/ep042/ep042.raw.txt \
  --outline outlines/ep042.outline.md \
  --output 03_review_draft/ep042/ep042.review.md \
  --ep-id ep042 \
  --speaker-map '{"发言人1": "GuestName", "发言人2": "Host1", "发言人3": "Host2"}' \
  --corrections corrections.json \
  --chapters chapters.json \
  --title "Episode Title"
```

### Phase 4: Human Review

Present the review draft to the user. The `## 疑点清单` section lists all uncertain items needing human confirmation.

### Phase 5: Finalize (after human confirmation)

1. Update the review draft with confirmed terms.
2. Write confirmed terms to `glossary/epXXX_confirmed_terms.md`.
3. Generate final transcript at `04_final_text/epXXX/epXXX.final.md`.
4. Update manifest: `human_final_review = true`.

## ASR Correction Strategy

Corrections are applied in order of confidence:

1. **Speaker names**: Map `发言人1/2/3` to real names from self-introductions.
2. **High-confidence replacements**: Exact string matches with no ambiguity.
3. **Context-dependent corrections**: Replacements depending on surrounding text.
4. **Uncertain items**: Flagged in the questions list, not auto-corrected.

For detailed ASR error patterns, see `references/asr_patterns.md`.

## Glossary Management

- Terms confirmed in one episode are automatically applied to future episodes.
- Each episode's confirmed terms are saved as `glossary/epXXX_confirmed_terms.md`.
- Cross-episode accumulation improves accuracy over time.

## Conservation & Safety

When transcript content involves:
- Wild plant/animal protection
- Illegal collection / poaching
- Conservation status / protected species
- Regulatory compliance

Apply conservative treatment: do not enhance, rewrite, or embellish facts. Preserve original meaning and flag for human review.

## Resources

### scripts/
- `import_docx.py` - Extract text from docx ASR exports
- `build_review.py` - Build review draft from raw text + outline

### template/
- `sample_outline.md` - Outline format reference
- `glossary_template.md` - Glossary file format guide
- `corrections_empty.json` - Empty corrections template (ready to fill)
- `chapters_empty.json` - Empty chapters template (ready to fill)
- `manifest_template.json` - Per-episode manifest template

### references/
- `asr_patterns.md` - Common ASR error patterns and correction strategies

### assets/
- `manifest_template.json` - Template for per-episode manifest files

### examples/
- `corrections.json` - Sample ASR correction rules (21 rules)
- `chapters.json` - Sample chapter definitions (9 chapters)
- `speaker_map.json` - Sample speaker mapping

### Root
- `init_project.sh` - One-command project scaffold (creates dirs + copies templates)
