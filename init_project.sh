#!/usr/bin/env bash
#
# Podcast Transcript Project Scaffold
#
# Creates the standard directory structure for a podcast transcript
# proofreading project. Run this once in a new project folder.
#
# Usage:
#   ./init_project.sh                    # create structure in current dir
#   ./init_project.sh /path/to/project   # create structure in target dir
#
set -euo pipefail

TARGET_DIR="${1:-.}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- Directory structure ---
DIRS=(
  "00_inbox"
  "01_raw_docx"
  "02_normalized_text"
  "03_review_draft"
  "04_final_text"
  "05_agent_chunks"
  "outlines"
  "glossary"
  "manifests"
  "config/by_ep"
)

echo "Creating podcast transcript project at: $(cd "$TARGET_DIR" 2>/dev/null && pwd || echo "$TARGET_DIR")"
echo ""

# Create directories with .gitkeep
for dir in "${DIRS[@]}"; do
  fullpath="$TARGET_DIR/$dir"
  mkdir -p "$fullpath"
  touch "$fullpath/.gitkeep"
  echo "  [dir]  $dir/"
done

# --- Copy templates ---
copy_template() {
  local src="$SCRIPT_DIR/template/$1"
  local dst="$TARGET_DIR/$2"
  if [[ -f "$src" ]]; then
    if [[ -e "$dst" ]]; then
      echo "  [keep] $2"
    else
      cp "$src" "$dst"
      echo "  [file] $2"
    fi
  fi
}

echo ""

# Empty corrections file (ready to fill in)
copy_template "corrections_empty.json" "corrections.json"

# Empty global speaker map
copy_template "speaker_map_empty.json" "speaker_map.json"

# Glossary template
copy_template "glossary_template.md" "glossary/README.md"

# Per-episode config guide
copy_template "by_ep_readme.md" "config/by_ep/README.md"

# Sample outline (for reference)
copy_template "sample_outline.md" "outlines/sample_outline.md"

# NOTE: manifests/ must contain nothing but generated manifests.
# `status` globs manifests/*.json, so a template file dropped in there
# shows up as a foreign manifest on every run. The reference copy stays
# in the skill at template/manifest_template.json.

echo ""
echo "Done! Project structure created."
echo ""
echo "Next steps:"
echo "  1. Drop your ASR export into 00_inbox/ (.docx/.txt/.md/.srt/.vtt)"
echo "  2. Write outlines/ep001.outline.md (copy outlines/sample_outline.md)"
echo "  3. Preflight the outline, then prepare:"
echo ""
echo "  python3 $SCRIPT_DIR/scripts/podcast_proofreader.py check-outline \\"
echo "    outlines/ep001.outline.md"
echo "  python3 $SCRIPT_DIR/scripts/podcast_proofreader.py prepare \\"
echo "    --project . --ep-id ep001 --input 00_inbox/your_episode.docx"
echo ""
echo "Per-episode corrections/speaker maps/chapters go in config/by_ep/"
echo "and are picked up automatically. See config/by_ep/README.md."
