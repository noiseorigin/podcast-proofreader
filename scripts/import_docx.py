#!/usr/bin/env python3
"""
Podcast ASR Transcript Importer

Extracts plain text from a docx ASR export file and saves it as a normalized
text file. Also copies the original docx to the raw_docx directory.

Usage:
    python import_docx.py --input "00_inbox/episode.docx" --ep-id ep042 --output-dir 02_normalized_text

    # With raw docx copy
    python import_docx.py --input "00_inbox/episode.docx" --ep-id ep042 \
        --output-dir 02_normalized_text --raw-dir 01_raw_docx
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime


def extract_text_from_docx(docx_path: str) -> str:
    """Extract text from a docx file using python-docx."""
    try:
        import docx
    except ImportError:
        print("Error: python-docx not installed. Install with: pip install python-docx", file=sys.stderr)
        sys.exit(1)

    doc = docx.Document(docx_path)
    lines = [p.text for p in doc.paragraphs]
    return "\n".join(lines)


def create_manifest(ep_id: str, title: str, source_path: str,
                    raw_docx_path: str, normalized_path: str,
                    manifest_dir: str = "manifests"):
    """Create or update a manifest JSON file for the episode."""
    manifest_path = os.path.join(manifest_dir, f"{ep_id}.json")

    manifest = {
        "episode_id": ep_id,
        "episode_number": int(ep_id.replace("ep", "")),
        "title": title,
        "source": {
            "type": "asr_export",
            "original_path": source_path,
            "managed_raw_docx": raw_docx_path,
            "normalized_text": normalized_path
        },
        "status": {
            "raw_docx_copied": True,
            "text_extracted": True,
            "ai_review_draft": False,
            "human_final_review": False,
            "agent_chunks_exported": False
        },
        "notes": f"Imported on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "outputs": {},
        "proofreading": {},
        "knowledge_base": {}
    }

    os.makedirs(manifest_dir, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return manifest_path


def main():
    parser = argparse.ArgumentParser(description="Import podcast ASR docx transcript")
    parser.add_argument("--input", required=True, help="Path to the input docx file")
    parser.add_argument("--ep-id", required=True, help="Episode ID, e.g. ep042")
    parser.add_argument("--output-dir", default="02_normalized_text",
                        help="Output directory for normalized text")
    parser.add_argument("--raw-dir", default=None,
                        help="Directory to copy raw docx (e.g. 01_raw_docx). Skip if not provided.")
    parser.add_argument("--manifest-dir", default="manifests",
                        help="Directory for manifest files")
    parser.add_argument("--title", default="", help="Episode title (optional)")

    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    ep_id = args.ep_id

    # Extract text
    print(f"Extracting text from: {input_path}")
    text = extract_text_from_docx(input_path)
    print(f"Extracted {len(text)} characters")

    # Save normalized text
    output_ep_dir = os.path.join(args.output_dir, ep_id)
    os.makedirs(output_ep_dir, exist_ok=True)
    output_path = os.path.join(output_ep_dir, f"{ep_id}.raw.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Normalized text saved to: {output_path}")

    # Copy raw docx if requested
    raw_docx_path = ""
    if args.raw_dir:
        raw_ep_dir = os.path.join(args.raw_dir, ep_id)
        os.makedirs(raw_ep_dir, exist_ok=True)
        raw_docx_path = os.path.join(raw_ep_dir, os.path.basename(input_path))
        shutil.copy2(input_path, raw_docx_path)
        print(f"Raw docx copied to: {raw_docx_path}")

    # Create manifest
    title = args.title or os.path.splitext(os.path.basename(input_path))[0]
    manifest_path = create_manifest(
        ep_id=ep_id,
        title=title,
        source_path=input_path,
        raw_docx_path=raw_docx_path,
        normalized_path=output_path,
        manifest_dir=args.manifest_dir
    )
    print(f"Manifest created at: {manifest_path}")

    print(f"\nDone! Episode {ep_id} imported successfully.")
    print(f"  Normalized text: {output_path}")
    print(f"  Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
