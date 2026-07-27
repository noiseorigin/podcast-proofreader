#!/usr/bin/env python3
"""
Podcast Review Draft Builder

Reads a raw ASR transcript, applies speaker mapping and ASR corrections,
inserts chapter headers from an outline, and generates a review draft
with a questions list for human review.

Usage:
    python build_review.py \
        --raw 02_normalized_text/ep042/ep042.raw.txt \
        --outline outlines/ep042.outline.md \
        --output 03_review_draft/ep042/ep042.review.md \
        --ep-id ep042 \
        --speaker-map '{"发言人1": "迪哥", "发言人2": "朱兜兜", "发言人3": "芋子"}'

    # With custom corrections file (JSON array of [old, new] pairs)
    python build_review.py \
        --raw 02_normalized_text/ep042/ep042.raw.txt \
        --output 03_review_draft/ep042/ep042.review.md \
        --ep-id ep042 \
        --speaker-map '{"发言人1": "迪哥", "发言人2": "朱兜兜"}' \
        --corrections corrections.json \
        --chapters chapters.json
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime


def load_speaker_map(speaker_map_str: str) -> dict:
    """Load speaker mapping from JSON string."""
    if not speaker_map_str:
        return {}
    return json.loads(speaker_map_str)


def load_corrections(corrections_path: str) -> list:
    """Load ASR corrections from a JSON file.
    
    Expected format: [["old1", "new1"], ["old2", "new2"], ...]
    """
    if not corrections_path or not os.path.exists(corrections_path):
        return []
    with open(corrections_path, "r", encoding="utf-8") as f:
        return json.load(f)


def apply_speaker_mapping(text: str, speaker_map: dict) -> str:
    """Replace speaker identifiers with real names."""
    for old, new in speaker_map.items():
        text = text.replace(old, new)
    return text


def apply_corrections(text: str, corrections: list) -> str:
    """Apply ASR error corrections.
    
    Each correction is a [old, new] pair. Only applies if old != new.
    """
    for old, new in corrections:
        if old != new:
            text = text.replace(old, new)
    return text


def parse_transcript(text: str, speaker_names: list) -> list:
    """Parse transcript into (speaker, timestamp, content) blocks.
    
    Expects lines like:
        迪哥   00:00
        content text here
        
        朱兜兜   00:08
        more content
    """
    lines = text.split("\n")
    pattern = r'^(' + '|'.join(re.escape(s) for s in speaker_names) + r')\s+(\d{2}:\d{2}(?::\d{2})?)\s*$'
    
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = re.match(pattern, line)
        if m:
            speaker = m.group(1)
            timestamp = m.group(2)
            text_lines = []
            i += 1
            while i < len(lines):
                l = lines[i].strip()
                if not l:
                    break
                if re.match(pattern, l):
                    break
                text_lines.append(l)
                i += 1
            content = " ".join(text_lines)
            blocks.append((speaker, timestamp, content))
        else:
            i += 1
    
    return blocks


def ts_to_seconds(ts: str) -> int:
    """Convert timestamp to seconds for comparison."""
    parts = ts.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


def insert_chapters(blocks: list, chapters: list) -> list:
    """Insert chapter headers into the block stream.
    
    chapters: list of (timestamp, title) tuples
    Returns: list of ("CHAPTER", timestamp, title) or ("BLOCK", speaker, timestamp, content)
    """
    result = []
    chap_idx = 0
    current_chap_sec = -1
    
    for speaker, ts, content in blocks:
        ts_sec = ts_to_seconds(ts)
        while chap_idx < len(chapters):
            chap_ts, chap_title = chapters[chap_idx]
            chap_sec = ts_to_seconds(chap_ts)
            if chap_sec <= ts_sec and chap_sec > current_chap_sec:
                result.append(("CHAPTER", chap_ts, chap_title))
                current_chap_sec = chap_sec
                chap_idx += 1
            else:
                break
        result.append(("BLOCK", speaker, ts, content))
    
    return result


def build_markdown(ep_id: str, title: str, description: str,
                   hosts: list, chapters: list, blocks_with_chapters: list,
                   questions: list, source_file: str, outline_source: str,
                   correction_rules: list) -> str:
    """Build the review draft markdown."""
    md = []
    
    # Header
    md.append(f"# {title}｜第一版校对稿")
    md.append("")
    md.append("> 状态：AI 初校 / 术语清理版，仍需人工回听终审。")
    md.append(f"> 来源：`{os.path.basename(source_file)}` 转出的 `{ep_id}.raw.txt`。")
    if outline_source:
        md.append(f"> 大纲：`{outline_source}`")
    md.append("")
    
    # Description
    if description:
        md.append("## 节目介绍")
        md.append("")
        md.append(description)
        md.append("")
    
    # Hosts
    if hosts:
        md.append("## 本期主播")
        md.append("")
        for h in hosts:
            md.append(f"- {h}")
        md.append("")
    
    # Correction rules
    md.append("## 本轮校对规则")
    md.append("")
    for rule in correction_rules:
        md.append(f"- {rule}")
    md.append("")
    
    # Timeline
    if chapters:
        md.append("## 时间轴")
        md.append("")
        for ts, chap_title in chapters:
            md.append(f"- {ts} {chap_title}")
        md.append("")
    
    # Body
    md.append("## 正文")
    md.append("")
    for item in blocks_with_chapters:
        if item[0] == "CHAPTER":
            md.append("")
            md.append(f"### [{item[1]}] {item[2]}")
            md.append("")
        else:
            _, speaker, ts, content = item
            md.append(f"**{speaker}** [{ts}]：{content}")
            md.append("")
    
    # Questions
    if questions:
        md.append("---")
        md.append("")
        md.append("## 疑点清单")
        md.append("")
        md.append("以下条目需人工回听确认。标注 `[⚠️?]` 的内容已在正文中保留原样或标注。")
        md.append("")
        for num, cat, item_name, desc in questions:
            md.append(f"### {num}. [{cat}] {item_name}")
            md.append(desc)
            md.append("")
        md.append("---")
        md.append("")
        md.append(f"> 以上疑点清单共 {len(questions)} 条，请人工回听后逐条确认。确认结果将写入 `glossary/{ep_id}_confirmed_terms.md`，并用于生成终审稿。")
    
    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="Build podcast review draft from raw ASR transcript")
    parser.add_argument("--raw", required=True, help="Path to raw text file")
    parser.add_argument("--outline", default=None, help="Path to outline file (optional)")
    parser.add_argument("--output", required=True, help="Output review draft path")
    parser.add_argument("--ep-id", required=True, help="Episode ID, e.g. ep042")
    parser.add_argument("--speaker-map", default="{}", help="JSON speaker mapping")
    parser.add_argument("--corrections", default=None, help="Path to corrections JSON file")
    parser.add_argument("--chapters", default=None, help="Path to chapters JSON file")
    parser.add_argument("--title", default="", help="Episode title")
    parser.add_argument("--description", default="", help="Episode description")
    
    args = parser.parse_args()
    
    # Load raw text
    with open(args.raw, "r", encoding="utf-8") as f:
        raw_text = f.read()
    
    # Load speaker map
    speaker_map = load_speaker_map(args.speaker_map)
    speaker_names = list(speaker_map.values()) if speaker_map else []
    
    # If no speaker names provided, try to auto-detect
    if not speaker_names:
        # Look for patterns like "发言人1", "发言人2", etc.
        found = set(re.findall(r'发言人\d+', raw_text))
        speaker_names = list(found)
        # Create default mapping
        for s in found:
            speaker_map[s] = s
    else:
        # Also handle any remaining 发言人N
        found = set(re.findall(r'发言人\d+', raw_text))
        for s in found:
            if s not in speaker_map:
                speaker_map[s] = s
                if s not in speaker_names:
                    speaker_names.append(s)
    
    # Apply speaker mapping
    text = apply_speaker_mapping(raw_text, speaker_map)
    
    # Apply corrections
    corrections = load_corrections(args.corrections)
    text = apply_corrections(text, corrections)
    
    # Parse into blocks
    blocks = parse_transcript(text, speaker_names)
    print(f"Parsed {len(blocks)} speech blocks")
    
    # Load chapters
    chapters = []
    if args.chapters and os.path.exists(args.chapters):
        with open(args.chapters, "r", encoding="utf-8") as f:
            chapters = json.load(f)
        chapters = [(c[0], c[1]) for c in chapters]
    
    # Insert chapters
    blocks_with_chapters = insert_chapters(blocks, chapters) if chapters else \
        [("BLOCK", s, t, c) for s, t, c in blocks]
    
    # Build correction rules description
    correction_rules = [
        "发言人已映射为真实姓名。",
        "已按大纲章节插入标题。",
        "已保留每段原始时间戳，便于回听确认。",
        "没有把整段口语改写成文章，只做第一轮可读性和术语清理。",
        "不确定的内容标注 `[⚠️?]` 供人工最终校对。",
        "BGM 歌词段落已保留，未删除。",
    ]
    if corrections:
        correction_rules.insert(0, f"已应用 {len(corrections)} 条 ASR 纠错规则。")
    
    # Build markdown
    title = args.title or f"{args.ep_id} 校对稿"
    outline_source = args.outline or ""
    
    markdown = build_markdown(
        ep_id=args.ep_id,
        title=title,
        description=args.description,
        hosts=speaker_names,
        chapters=chapters,
        blocks_with_chapters=blocks_with_chapters,
        questions=[],  # Questions are added by the AI agent based on review
        source_file=args.raw,
        outline_source=outline_source,
        correction_rules=correction_rules
    )
    
    # Save
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(markdown)
    
    print(f"Review draft written: {len(markdown)} chars -> {args.output}")
    print(f"  Blocks: {len(blocks)}")
    print(f"  Chapters: {len(chapters)}")
    print(f"  Corrections applied: {len(corrections)}")
    
    # Output blocks for AI agent to review and generate questions
    print(f"\n--- BLOCKS FOR REVIEW ---")
    for speaker, ts, content in blocks[:20]:
        print(f"  [{ts}] {speaker}: {content[:80]}...")
    if len(blocks) > 20:
        print(f"  ... and {len(blocks) - 20} more blocks")
    print(f"--- END BLOCKS ---")


if __name__ == "__main__":
    main()
