---
name: podcast-proofreader
description: Podcast transcript review for creators. Turns timestamped DOCX ASR exports into structured Markdown drafts, maps speakers, applies confirmed corrections, inserts chapters, and flags uncertain passages for human review. Optimized for Chinese podcasts. Use for 播客校对、根据大纲校对、导入播客文字稿、生成初校稿、ASR 纠错, or finalizing a reviewed transcript.
version: 1.0.0
author: noiseorigin
license: MIT
homepage: https://github.com/noiseorigin/podcast-proofreader
compatibility: Python 3.10+ and Bash; python-docx is required for DOCX imports.
user-invocable: true
metadata: {"openclaw":{"emoji":"🎙️","homepage":"https://github.com/noiseorigin/podcast-proofreader"},"hermes":{"tags":["Podcast","ASR","Proofreading"]}}
---

# Podcast Proofreader

Help a podcast creator turn a timestamped ASR transcript into a draft that is fast to review and safe to finalize.

The creator should be able to work in natural language. Do not make them manage internal files unless they ask for manual commands.

## Current Scope

Use this workflow for:

- DOCX ASR exports with speaker labels and timestamps
- Local Markdown episode outlines
- Speaker-name mapping
- Confirmed exact replacements
- Timestamp-based chapter insertion
- Contextual review and a human-verification list
- Final Markdown transcripts after confirmation

## Resolve the Skill Directory

Before running a bundled script, determine the directory containing this `SKILL.md`. Call it `SKILL_DIR`.

Resolve every bundled path against `SKILL_DIR`, not against the creator's transcript workspace. For example:

```bash
python3 "$SKILL_DIR/scripts/import_docx.py" --help
```

Never assume the current working directory is the Skill directory.

## Prerequisite Check

DOCX import requires Python 3.10+ and `python-docx`.

Check with:

```bash
python3 -c "import docx"
```

If it is missing, explain the requirement and ask before running:

```bash
python3 -m pip install python-docx
```

## Creator-First Interaction

When the creator asks to review an episode:

1. Locate the DOCX transcript.
2. Determine the episode ID, such as `ep042`.
3. Locate the local Markdown outline if one is available.
4. Ask only for information that cannot be inferred safely, especially speaker identities.
5. Run the mechanical steps yourself.
6. Present the review draft and its questions, not a long implementation log.

Never invent a speaker name, proper noun, number, quotation, or factual claim.

## Workspace Setup

If the creator does not have a workspace, run:

```bash
bash "$SKILL_DIR/init_project.sh" /path/to/PodcastTranscripts
```

The supported workspace is:

```text
PodcastTranscripts/
├── 00_inbox/
├── 01_raw_docx/
├── 02_normalized_text/
├── 03_review_draft/
├── 04_final_text/
├── outlines/
├── glossary/
├── manifests/
├── corrections.json
└── chapters.json
```

## Workflow

### Phase 1: Import the DOCX

Run from the transcript workspace:

```bash
python3 "$SKILL_DIR/scripts/import_docx.py" \
  --input "00_inbox/episode.docx" \
  --ep-id ep042 \
  --output-dir 02_normalized_text \
  --raw-dir 01_raw_docx \
  --manifest-dir manifests \
  --title "Episode title"
```

Verify that these files exist:

- `01_raw_docx/ep042/<source-file>.docx`
- `02_normalized_text/ep042/ep042.raw.txt`
- `manifests/ep042.json`

Do not modify the archived DOCX or normalized raw text after import.

### Phase 2: Read the Outline

Read the local outline before building the draft.

Use it to identify:

- likely speaker names;
- confirmed spelling of names, brands, and technical terms;
- chapter titles and timestamps;
- claims or quotations that need careful verification.

The Python script records the outline path but does not understand the outline semantically. Outline comparison is the agent's responsibility.

If speaker identities are unclear, ask the creator. Do not guess.

### Phase 3: Prepare Mechanical Rules

Use `corrections.json` only for exact replacements that are already confirmed:

```json
[
  ["Open AI", "OpenAI"],
  ["Chat G P T", "ChatGPT"]
]
```

Use `chapters.json` for timestamp/title pairs:

```json
[
  ["00:00", "开场"],
  ["04:30", "嘉宾经历"]
]
```

Context-dependent or uncertain corrections belong in the questions list, not in `corrections.json`.

### Phase 4: Build the Structured Draft

```bash
python3 "$SKILL_DIR/scripts/build_review.py" \
  --raw 02_normalized_text/ep042/ep042.raw.txt \
  --outline outlines/ep042.outline.md \
  --output 03_review_draft/ep042/ep042.review.md \
  --ep-id ep042 \
  --speaker-map '{"发言人1":"嘉宾","发言人2":"主播"}' \
  --corrections corrections.json \
  --chapters chapters.json \
  --title "Episode title"
```

Verify that speech blocks were parsed. If the script reports zero blocks, check the speaker labels, timestamps, and speaker map before continuing.

### Phase 5: Perform Contextual Review

Read the entire draft and compare it with the outline.

Review especially:

- inconsistent names or titles;
- unfamiliar proper nouns and brands;
- suspicious numbers, dates, URLs, and negation;
- broken grammar that may indicate ASR corruption;
- abrupt topic changes;
- factual, legal, medical, or financial claims that should not be silently rewritten.

Apply only high-confidence corrections. Mark uncertain text with `[⚠️?]` and append:

```markdown
---

## 疑点清单

### 1. [类别] 简短标题
- 时间戳：00:12:34
- 原文：……
- 疑点：……
- 请确认：……
```

Every question must carry a timestamp and a short transcript excerpt for replay.

After this review is complete, update `manifests/ep042.json`:

- `status.ai_review_draft = true`
- `outputs.review_draft` points to the review file
- record the number of unresolved questions when practical

### Phase 6: Human Confirmation

Present the questions list to the creator. Do not create a final transcript while unresolved questions remain unless the creator explicitly asks to preserve them.

### Phase 7: Finalize

After the creator confirms the questions:

1. Apply the confirmed answers to the review draft.
2. Save confirmed episode terminology to `glossary/ep042_confirmed_terms.md`.
3. Write `04_final_text/ep042/ep042.final.md`.
4. Remove review-only markers that have been resolved.
5. Update `manifests/ep042.json`:
   - `status.human_final_review = true`
   - `outputs.final_text` points to the final file

Do not overwrite the raw transcript or the first review draft without explicit permission.

## Review Principles

1. Preserve meaning before improving style.
2. Correct only confirmed or unambiguous errors automatically.
3. Keep timestamps intact.
4. Flag uncertainty instead of guessing.
5. Treat previous glossary entries as references, not universal truth.
6. Require human confirmation before finalization.

## Bundled Resources

- `scripts/import_docx.py` — extract DOCX text, archive the source, and create a manifest
- `scripts/build_review.py` — map speakers, apply exact corrections, insert chapters, and write the structured draft
- `references/asr_patterns.md` — generic Chinese podcast ASR review patterns
- `template/sample_outline.md` — local outline example
- `template/corrections_empty.json` — empty correction rules
- `template/chapters_empty.json` — empty chapter definitions
- `template/glossary_template.md` — confirmed-term format
- `template/manifest_template.json` — episode status schema
