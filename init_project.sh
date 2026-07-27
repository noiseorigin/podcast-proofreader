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
  "outlines"
  "glossary"
  "manifests"
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

# Empty chapters file (ready to fill in)
copy_template "chapters_empty.json" "chapters.json"

# Glossary template
copy_template "glossary_template.md" "glossary/README.md"

# Sample outline (for reference)
copy_template "sample_outline.md" "outlines/sample_outline.md"

# Manifest template
copy_template "manifest_template.json" "manifests/manifest_template.json"

echo ""
echo "Done! Project structure created."
echo ""
echo "Next steps:"
echo "  1. Drop your ASR export (.docx) into 00_inbox/"
echo "  2. Write your show outline in outlines/ (see sample_outline.md)"
echo "  3. Ask your agent to import and review the episode"
echo ""
echo "Manual import command:"
echo "  python3 $SCRIPT_DIR/scripts/import_docx.py \\"
echo "    --input 00_inbox/your_episode.docx --ep-id ep001 \\"
echo "    --output-dir 02_normalized_text --raw-dir 01_raw_docx \\"
echo "    --manifest-dir manifests"
