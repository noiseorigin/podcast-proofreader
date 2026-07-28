# Podcast Proofreader

[简体中文](README.md) | **English**

An ASR transcript review Skill made for podcast creators. It produces:

1. an editor-facing review draft with timestamps and numbered questions;
2. a confirmed transcript, structured timeline, and JSONL retrieval chunks.

The script handles deterministic transformations, while the agent reviews context. Anything
uncertain must be confirmed by a person before finalization.

## Quick start

### 1. Install the Skill

Use the universal Agent Skills installer. It detects installed agents automatically:

```bash
npx skills add noiseorigin/podcast-proofreader --global --copy
```

To target OpenClaw and Hermes explicitly:

```bash
npx skills add noiseorigin/podcast-proofreader \
  --global \
  --agent openclaw \
  --agent hermes-agent \
  --copy \
  --yes
```

Keep `--copy`: some agent hosts do not discover a skill directory through a symlink.

### 2. Check the environment

```bash
python3 scripts/podcast_proofreader.py doctor
```

The recommended workflow needs Python 3.10+ only. DOCX parsing is built in and does not
require `python-docx`.

### 3. Ask your agent to create a workspace

After installation, tell your agent:

```text
Create a podcast transcript review workspace at ~/PodcastTranscripts.
```

The Skill creates the inbox, outline, review draft, final transcript, glossary, and status directories.

### 4. Add an episode

- Put the ASR transcript in `00_inbox/`.
- Save the local episode outline as `outlines/ep042.outline.md`.

Then ask:

```text
Import 00_inbox/episode042.docx as ep042 and review it against
outlines/ep042.outline.md. Do not guess uncertain names, terms, or
sentences; add them to the questions list with timestamps.
```

If speaker identities are unclear, the agent should ask you instead of inventing names.

## What you get

```text
03_review_draft/ep042/ep042.editor-review.md
```

Each question includes an ID, timestamp, speaker, source text, suggestion, and reason. The
editor can reply with `accept`, `keep`, `replace`, or `delete`.

After checking those timestamps, tell the agent:

```text
I have confirmed the questions. Update the glossary and create the final
ep042 transcript.
```

After every question is resolved, the final delivery contains:

```text
04_final_text/ep042/ep042.final.md
04_final_text/ep042/ep042.timeline.json
05_agent_chunks/ep042/ep042.chunks.jsonl
```

## Current support

- `.docx`, `.txt`, `.md`, `.srt`, and `.vtt` transcripts
- Local Markdown episode outlines
- Explicit mapping for labels such as `发言人1` and `Speaker 1`
- Exact string correction rules
- Outline-driven chapter insertion
- Agent-assisted contextual review and questions
- Human-confirmed Markdown transcripts
- Structured timelines and retrieval/RAG chunks
- Safe reruns, input fingerprints, and workflow state gates

## Compatible agents

The workflow is model-independent. An agent can run it when it can read and write local files,
execute Python, and pause for human confirmation.

| Agent | Integration |
|---|---|
| OpenAI Codex | Install the Skill; `agents/openai.yaml` is included |
| Claude Code | Auto-detected, or select `--agent claude-code` |
| OpenClaw / Hermes | Select the agent explicitly with the universal installer |
| Cursor / Windsurf | Auto-detected or explicitly selected by the installer |
| Cline / Roo Code | Auto-detected or explicitly selected by the installer |
| OpenCode / Gemini CLI / Pi | Auto-detected or explicitly selected by the installer |
| WorkBuddy and similar local agents | Supported when they can import `SKILL.md` and run local commands |

A chat-only agent without filesystem, Python, or persistent state access cannot complete the
workflow independently.

## Before you start

The minimum input is a readable, non-empty transcript. Before processing, confirm:

- a stable episode ID, such as `ep042`;
- a writable project directory;
- that the transcript, audio, and outline belong to the same episode version.

Strongly recommended inputs are the matching audio, episode outline, known speaker names,
confirmed terminology, total duration, and a person who can resolve uncertain passages.

Missing optional inputs do not block the workflow: without an outline, the title falls back to
the filename and the transcript uses one full-length chapter; without audio, questions require an
external replay source; without a speaker map, generic speaker labels become questions; without
duration, the last chapter end remains unknown.

Users do not need to write `agent-review.json` or `answers.json`; the agent creates them from
its full review and the editor's explicit replies.

## Expected transcript format

```text
Speaker 1   00:00
Welcome to the show.

Speaker 2   00:08
Thanks for having me.
```

Both `MM:SS` and `HH:MM:SS` timestamps are supported. Labels must be included in the speaker map when they are not in the default Chinese `发言人N` form.

## Workspace layout

```text
PodcastTranscripts/
├── 00_inbox/              # New transcript exports
├── 01_raw_docx/           # Archived source files
├── 02_normalized_text/    # Extracted plain text
├── 03_review_draft/       # Structured review and editor questions
├── 04_final_text/         # Final transcript and timeline
├── 05_agent_chunks/       # Retrieval/RAG chunks
├── outlines/              # Local episode outlines
├── glossary/              # Human-confirmed terminology
├── manifests/             # Per-episode processing status
├── speaker_map.json       # Confirmed speaker identities
└── corrections.json       # Confirmed exact replacements
```

The source DOCX and normalized raw text remain unchanged. Drafts and final transcripts are written to separate directories.

## Manual commands

Most podcast creators can use natural-language prompts and skip this section. These commands are useful for troubleshooting and automation.

### Initialize a project

```bash
python3 scripts/podcast_proofreader.py init \
  --project ~/PodcastTranscripts
```

### Prepare an episode

```bash
python3 scripts/podcast_proofreader.py prepare \
  --project ~/PodcastTranscripts \
  --input ~/PodcastTranscripts/00_inbox/episode042.docx \
  --outline ~/PodcastTranscripts/outlines/ep042.outline.md \
  --audio ~/PodcastTranscripts/audio/episode042.mp3 \
  --ep-id ep042 \
  --duration 01:12:30
```

### Check progress

```bash
python3 scripts/podcast_proofreader.py status \
  --project ~/PodcastTranscripts \
  --ep-id ep042
```

The agent normally generates the JSON inputs for `agent-review` and `resolve`. Full commands and
schemas are documented in [SKILL.md](SKILL.md) and
[references/contracts.md](references/contracts.md).

The legacy `init_project.sh`, `scripts/import_docx.py`, and `scripts/build_review.py` remain
available for existing automation. The legacy DOCX importer still requires `python-docx`.

## Configuration

### `corrections.json`

Only include replacements that are already confirmed:

```json
[
  ["Open AI", "OpenAI"],
  ["Chat G P T", "ChatGPT"]
]
```

Do not add uncertain guesses here; put them in the questions list.

Chapter timestamps and titles now come from the Markdown outline. See
[template/sample_outline.md](template/sample_outline.md).

## Review policy

1. Correct only high-confidence or human-confirmed errors automatically.
2. Preserve and flag uncertain names, brands, numbers, negation, and factual claims.
3. Do not turn spoken language into a rewritten article or change the speaker's meaning.
4. Every question must include a timestamp.
5. Create the final transcript only after human confirmation.

## Privacy

Podcast transcripts may contain unpublished material or personal information. Before using a hosted agent, review that service's data policy. Process sensitive episodes in a controlled environment.

## Development and tests

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
```

## License

[MIT](LICENSE)
