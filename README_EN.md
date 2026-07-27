# Podcast Proofreader

[简体中文](README.md) | **English**

An ASR transcript review Skill made for podcast creators.

Provide a DOCX transcript with speaker labels and timestamps, plus a local episode outline. The agent maps speakers, applies confirmed corrections, inserts chapters, and collects uncertain passages into a review list so you only replay the parts that need human judgment.

> The current release is optimized for Chinese-language podcasts, targets macOS/Linux command-line environments, and follows a review-first workflow. It does not rewrite uncertain speech as fact.

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

### 2. Install the DOCX dependency

```bash
python3 -m pip install python-docx
```

### 3. Ask your agent to create a workspace

After installation, tell your agent:

```text
Create a podcast transcript review workspace at ~/PodcastTranscripts.
```

The Skill creates the inbox, outline, review draft, final transcript, glossary, and status directories.

### 4. Add an episode

- Put the ASR DOCX export in `00_inbox/`.
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
03_review_draft/ep042/ep042.review.md
```

The review draft contains:

- mapped speaker names;
- original timestamps;
- chapter headings;
- high-confidence terminology corrections;
- a focused list of passages that need human verification.

After checking those timestamps, tell the agent:

```text
I have confirmed the questions. Update the glossary and create the final
ep042 transcript.
```

The final transcript is saved to:

```text
04_final_text/ep042/ep042.final.md
```

## Current support

- `.docx` ASR exports with speaker labels and timestamps
- Local Markdown episode outlines
- Explicit mapping for labels such as `发言人1` and `Speaker 1`
- Exact string correction rules
- Timestamp-based chapter insertion
- Agent-assisted contextual review and questions
- Human-approved Markdown transcripts

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
├── 00_inbox/              # New DOCX exports
├── 01_raw_docx/           # Archived source files
├── 02_normalized_text/    # Extracted plain text
├── 03_review_draft/       # Review drafts and questions
├── 04_final_text/         # Human-approved transcripts
├── outlines/              # Local episode outlines
├── glossary/              # Human-confirmed terminology
├── manifests/             # Per-episode processing status
├── corrections.json       # Confirmed exact replacements
└── chapters.json          # Chapter timestamps and titles
```

The source DOCX and normalized raw text remain unchanged. Drafts and final transcripts are written to separate directories.

## Manual commands

Most podcast creators can use natural-language prompts and skip this section. These commands are useful for troubleshooting and automation.

### Initialize a workspace

```bash
bash /path/to/podcast-proofreader/init_project.sh ~/PodcastTranscripts
```

### Import a DOCX transcript

```bash
cd ~/PodcastTranscripts

python3 /path/to/podcast-proofreader/scripts/import_docx.py \
  --input 00_inbox/episode042.docx \
  --ep-id ep042 \
  --output-dir 02_normalized_text \
  --raw-dir 01_raw_docx \
  --manifest-dir manifests \
  --title "Episode title"
```

### Build the structured draft

```bash
python3 /path/to/podcast-proofreader/scripts/build_review.py \
  --raw 02_normalized_text/ep042/ep042.raw.txt \
  --outline outlines/ep042.outline.md \
  --output 03_review_draft/ep042/ep042.review.md \
  --ep-id ep042 \
  --speaker-map '{"Speaker 1":"Guest","Speaker 2":"Host"}' \
  --corrections corrections.json \
  --chapters chapters.json \
  --title "Episode title"
```

The scripts only perform deterministic transformations. The agent—not `build_review.py`—compares meaning with the outline, reviews context, and appends uncertain passages.

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

### `chapters.json`

```json
[
  ["00:00", "Introduction"],
  ["04:30", "The guest's story"],
  ["18:20", "Main discussion"]
]
```

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
