#!/usr/bin/env python3
"""Agent-friendly podcast transcript proofreading workflow.

The command keeps deterministic work in code and leaves semantic judgement to
the agent and editor:

  init -> prepare -> agent-review -> resolve -> finalize
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


SCHEMA_MANIFEST = "podcast-proofreader.manifest.v1"
SCHEMA_REVIEW = "podcast-proofreader.review.v1"
SCHEMA_QUESTIONS = "podcast-proofreader.questions.v1"
SCHEMA_TIMELINE = "podcast-proofreader.timeline.v1"
SCHEMA_CHUNK = "podcast-proofreader.chunk.v1"
WORKFLOW_REVISION = 2

PROJECT_DIRS = (
    "00_inbox",
    "01_raw_docx",
    "02_normalized_text",
    "03_review_draft",
    "04_final_text",
    "05_agent_chunks",
    "outlines",
    "glossary",
    "manifests",
)


class WorkflowError(Exception):
    """A user-actionable workflow error."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def load_json(path: Path, label: str) -> Any:
    if not path.is_file():
        raise WorkflowError(f"{label}不存在：{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkflowError(
            f"{label}不是合法 JSON：{path}（第 {exc.lineno} 行，第 {exc.colno} 列）"
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise WorkflowError(f"无法读取{label}：{path}（{exc}）") from exc


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise WorkflowError(f"无法读取输入文件：{path}（{exc}）") from exc
    return digest.hexdigest()


def json_fingerprint(data: Any) -> str:
    payload = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_episode_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value):
        raise WorkflowError(
            "期号只能包含字母、数字、点、下划线和连字符，且不能包含路径符号。"
        )
    if value in {".", ".."}:
        raise WorkflowError("期号不能是 . 或 ..")
    return value


def derive_episode_id(path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", path.stem).strip(".-_").lower()
    if not stem:
        raise WorkflowError("无法从文件名推导期号，请显式传入 --ep-id。")
    return validate_episode_id(stem[:64])


def ensure_within(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise WorkflowError(f"输出路径越出项目目录：{resolved}")
    return resolved


def relative_to_project(path: Path | None, project: Path) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(project.resolve()))
    except ValueError:
        return str(path.resolve())


def parse_time(value: str) -> float:
    clean = value.strip().replace(",", ".")
    parts = clean.split(":")
    if len(parts) not in {2, 3}:
        raise WorkflowError(f"无法识别时间戳：{value}")
    try:
        numbers = [float(part) for part in parts]
    except ValueError as exc:
        raise WorkflowError(f"无法识别时间戳：{value}") from exc
    if any(not math.isfinite(number) for number in numbers):
        raise WorkflowError(f"时间戳必须是有限数值：{value}")
    if any(number < 0 for number in numbers):
        raise WorkflowError(f"时间戳不能为负数：{value}")
    if any(not number.is_integer() for number in numbers[:-1]):
        raise WorkflowError(f"时间戳的小时和分钟必须是整数：{value}")
    if len(numbers) == 2:
        minutes, seconds = numbers
        hours = 0
    else:
        hours, minutes, seconds = numbers
    if seconds >= 60 or (len(numbers) == 3 and minutes >= 60):
        raise WorkflowError(
            f"时间戳秒必须小于 60，三段式的分钟也必须小于 60：{value}"
        )
    return hours * 3600 + minutes * 60 + seconds


def format_time(seconds: float | int | None) -> str | None:
    if seconds is None:
        return None
    total = max(0, int(round(float(seconds))))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def read_text_with_fallback(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise WorkflowError(f"无法识别文本编码：{path}（建议保存为 UTF-8）")


def extract_docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise WorkflowError(f"不是有效的 DOCX 文件：{path}") from exc

    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise WorkflowError(f"DOCX 正文 XML 损坏：{path}") from exc
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = root.find(f".//{{{namespace}}}body")
    if body is None:
        raise WorkflowError(f"DOCX 缺少正文：{path}")

    def node_text(node: ElementTree.Element) -> str:
        values: list[str] = []
        for child in node.iter():
            if child.tag == f"{{{namespace}}}t" and child.text:
                values.append(child.text)
            elif child.tag == f"{{{namespace}}}tab":
                values.append("\t")
            elif child.tag in {
                f"{{{namespace}}}br",
                f"{{{namespace}}}cr",
            }:
                values.append("\n")
        return "".join(values).strip()

    def cell_text(cell: ElementTree.Element) -> str:
        paragraphs = [
            node_text(paragraph)
            for paragraph in cell.findall(f"./{{{namespace}}}p")
        ]
        return "\n".join(value for value in paragraphs if value)

    lines: list[str] = []
    for child in body:
        if child.tag == f"{{{namespace}}}p":
            lines.append(node_text(child))
        elif child.tag == f"{{{namespace}}}tbl":
            for row in child.findall(f"./{{{namespace}}}tr"):
                cells = [
                    cell_text(cell)
                    for cell in row.findall(f"./{{{namespace}}}tc")
                ]
                lines.append("\t".join(cell for cell in cells if cell))
    return "\n".join(lines)


def extract_source_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        text = extract_docx_text(path)
    elif suffix in {".txt", ".md", ".srt", ".vtt"}:
        text = read_text_with_fallback(path)
    else:
        raise WorkflowError(
            f"暂不支持 {suffix or '无扩展名'}；支持 .docx/.txt/.md/.srt/.vtt。"
        )
    if not text.strip():
        raise WorkflowError(f"输入文件没有可提取文字：{path}")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def strip_cue_markup(text: str) -> str:
    text = re.sub(r"</?v(?:\s+[^>]*)?>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def parse_subtitle(
    text: str, known_speakers: set[str]
) -> list[dict[str, Any]]:
    timing = re.compile(
        r"(?P<start>\d+:\d{2}(?::\d{2})?[.,]\d{3}|\d+:\d{2}(?::\d{2})?)"
        r"\s*-->\s*"
        r"(?P<end>\d+:\d{2}(?::\d{2})?[.,]\d{3}|\d+:\d{2}(?::\d{2})?)"
    )
    lines = text.splitlines()
    blocks: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        match = timing.search(lines[index])
        if not match:
            index += 1
            continue
        index += 1
        cue_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            cue_lines.append(lines[index].strip())
            index += 1
        raw_cue_text = " ".join(cue_lines)
        speaker = "未标注"
        voice_match = re.match(
            r"^<v(?:\.[^\s>]+)?\s+([^>]+)>(.*?)(?:</v>)?$",
            raw_cue_text,
            re.IGNORECASE,
        )
        if voice_match:
            speaker = voice_match.group(1).strip()
            cue_text = strip_cue_markup(voice_match.group(2))
        else:
            cue_text = strip_cue_markup(raw_cue_text)
            speaker_match = re.match(r"^([^：:]{1,30})[：:]\s*(.+)$", cue_text)
            if speaker_match and is_strong_speaker(
                speaker_match.group(1), known_speakers
            ):
                speaker = speaker_match.group(1).strip()
                cue_text = speaker_match.group(2).strip()
        if cue_text:
            blocks.append(
                {
                    "speaker": speaker,
                    "start_seconds": parse_time(match.group("start")),
                    "end_seconds": parse_time(match.group("end")),
                    "text": cue_text,
                }
            )
    return blocks


SPEAKER_HINT = re.compile(
    r"^(?:发言人|说话人|讲话人|speaker|host|guest)\s*[\w.-]*$",
    re.IGNORECASE,
)
TIME_TOKEN = r"\d+:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?"


def looks_like_speaker(candidate: str, known: set[str]) -> bool:
    clean = candidate.strip().strip("[]")
    if clean in known or SPEAKER_HINT.fullmatch(clean):
        return True
    if 0 < len(clean) <= 20 and not re.search(r"[。！？!?，,；;]", clean):
        return len(clean.split()) <= 3
    return False


def is_strong_speaker(candidate: str, known: set[str]) -> bool:
    clean = candidate.strip().strip("[]")
    return clean in known or bool(SPEAKER_HINT.fullmatch(clean))


def detect_plain_header(
    line: str, known_speakers: set[str]
) -> tuple[str, float, str] | None:
    clean = line.strip()
    if not clean:
        return None

    timestamp_first = re.match(
        rf"^\[?(?P<ts>{TIME_TOKEN})\]?\s+(?P<rest>.+)$", clean
    )
    if timestamp_first:
        rest = timestamp_first.group("rest").strip()
        with_content = re.match(r"^(?P<speaker>[^：:]{1,30})[：:]\s*(?P<text>.*)$", rest)
        if with_content and looks_like_speaker(
            with_content.group("speaker"), known_speakers
        ):
            return (
                with_content.group("speaker").strip(),
                parse_time(timestamp_first.group("ts")),
                with_content.group("text").strip(),
            )
        if looks_like_speaker(rest, known_speakers):
            return rest, parse_time(timestamp_first.group("ts")), ""

    speaker_first = re.match(
        rf"^(?P<speaker>.+?)\s+\[?(?P<ts>{TIME_TOKEN})\]?"
        rf"(?:\s+(?P<text>.*))?$",
        clean,
    )
    if speaker_first:
        speaker = speaker_first.group("speaker")
        inline_text = (speaker_first.group("text") or "").strip()
        is_header = is_strong_speaker(speaker, known_speakers) or (
            not inline_text and looks_like_speaker(speaker, known_speakers)
        )
    else:
        is_header = False
    if speaker_first and is_header:
        return (
            speaker.strip(),
            parse_time(speaker_first.group("ts")),
            inline_text,
        )
    return None


def parse_plain_transcript(
    text: str, known_speakers: set[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    preamble: list[str] = []
    current: dict[str, Any] | None = None
    content_lines: list[str] = []

    def flush() -> None:
        nonlocal current, content_lines
        if current is None:
            return
        while content_lines and not content_lines[0].strip():
            content_lines.pop(0)
        while content_lines and not content_lines[-1].strip():
            content_lines.pop()
        content = "\n".join(content_lines).strip()
        if content:
            current["text"] = content
            blocks.append(current)
        current = None
        content_lines = []

    for line in text.splitlines():
        header = detect_plain_header(line, known_speakers)
        if header:
            flush()
            speaker, start_seconds, inline_text = header
            current = {
                "speaker": speaker,
                "start_seconds": start_seconds,
                "end_seconds": None,
                "text": "",
            }
            content_lines = [inline_text] if inline_text else []
        elif current is not None:
            content_lines.append(line)
        elif line.strip():
            preamble.append(line.strip())
    flush()

    if blocks and preamble:
        first_start = blocks[0]["start_seconds"]
        blocks.insert(
            0,
            {
                "speaker": "未标注",
                "start_seconds": 0,
                "end_seconds": first_start,
                "text": "\n".join(preamble),
            },
        )
    if not blocks:
        plain = "\n".join(line for line in text.splitlines() if line.strip()).strip()
        if not plain:
            raise WorkflowError("转写稿没有可用正文。")
        blocks = [
            {
                "speaker": "未标注",
                "start_seconds": 0,
                "end_seconds": None,
                "text": plain,
            }
        ]
        mode = "plain_text"
    else:
        mode = "speaker_timestamp"

    for index, block in enumerate(blocks):
        if block["end_seconds"] is None and index + 1 < len(blocks):
            block["end_seconds"] = blocks[index + 1]["start_seconds"]
    return blocks, {"mode": mode, "preamble_lines": len(preamble)}


def load_speaker_map(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    data = load_json(path, "发言人映射")
    if not isinstance(data, dict) or not all(
        isinstance(key, str) and isinstance(value, str) and value.strip()
        for key, value in data.items()
    ):
        raise WorkflowError("发言人映射必须是 JSON 对象：{\"发言人1\": \"张三\"}。")
    return {key.strip(): value.strip() for key, value in data.items()}


def load_corrections(path: Path | None) -> list[dict[str, str]]:
    if path is None:
        return []
    data = load_json(path, "纠错规则")
    if not isinstance(data, list):
        raise WorkflowError("纠错规则必须是 JSON 数组。")
    rules: list[dict[str, str]] = []
    seen: dict[str, str] = {}
    for index, item in enumerate(data, start=1):
        if (
            isinstance(item, list)
            and len(item) == 2
            and all(isinstance(value, str) for value in item)
        ):
            old, new = item
            rule = {"from": old, "to": new, "note": ""}
        elif isinstance(item, dict):
            old = item.get("from")
            new = item.get("to")
            if not isinstance(old, str) or not isinstance(new, str):
                raise WorkflowError(f"纠错规则第 {index} 项缺少字符串 from/to。")
            rule = {
                "from": old,
                "to": new,
                "note": str(item.get("note", "")),
            }
        else:
            raise WorkflowError(f"纠错规则第 {index} 项格式错误。")
        if not rule["from"]:
            raise WorkflowError(f"纠错规则第 {index} 项的 from 不能为空。")
        if rule["from"] in seen:
            if seen[rule["from"]] != rule["to"]:
                raise WorkflowError(
                    f"纠错规则冲突：{rule['from']} 同时映射到 "
                    f"{seen[rule['from']]} 和 {rule['to']}。"
                )
            continue
        seen[rule["from"]] = rule["to"]
        rules.append(rule)
    return rules


def parse_outline(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "path": "",
            "title": "",
            "description": "",
            "chapters": [],
            "people": [],
            "term_hints": [],
        }
    if not path.is_file():
        raise WorkflowError(f"节目大纲不存在：{path}")
    text = read_text_with_fallback(path)
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else ""
    sections: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        heading = re.match(r"^##\s+(.+)$", line)
        if heading:
            current = heading.group(1).strip()
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line)

    description = ""
    chapters: list[dict[str, Any]] = []
    people: list[str] = []
    term_hints: list[dict[str, str]] = []

    for name, lines in sections.items():
        joined = "\n".join(lines).strip()
        if any(key in name for key in ("节目介绍", "节目简介", "简介")):
            description = joined
        if any(key in name for key in ("时间轴", "章节")):
            for line in lines:
                if not re.match(r"^\s*[-*]\s+", line):
                    continue
                match = re.match(
                    rf"^\s*[-*]\s*\[?(?P<ts>{TIME_TOKEN})\]?\s+"
                    r"(?P<title>.+?)\s*$",
                    line,
                )
                if not match:
                    raise WorkflowError(
                        f"大纲时间轴格式错误：{line.strip()} "
                        "（应为“- 00:00 章节标题”）"
                    )
                chapters.append(
                    {
                        "start_seconds": parse_time(match.group("ts")),
                        "title": match.group("title").strip(),
                    }
                )
        if any(key in name for key in ("节目信息", "嘉宾", "主播")):
            for line in lines:
                match = re.match(r"^\s*[-*]\s*(?:主播|嘉宾)[：:]\s*(.+)$", line)
                if match:
                    for person in re.split(r"[、,，/]", match.group(1)):
                        clean = re.sub(r"（.*?）|\(.*?\)", "", person).strip()
                        if clean and clean not in people:
                            people.append(clean)
        if "术语" in name:
            for line in lines:
                if not line.strip().startswith("|"):
                    continue
                cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
                if len(cells) < 2 or all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                    continue
                if cells[0] in {"正确写法", "术语", "标准写法"}:
                    continue
                correct = cells[0]
                wrong = cells[1]
                note = cells[2] if len(cells) > 2 else ""
                if correct:
                    term_hints.append(
                        {"correct": correct, "wrong": wrong, "note": note}
                    )

    chapters.sort(key=lambda item: item["start_seconds"])
    for previous, current_chapter in zip(chapters, chapters[1:]):
        if previous["start_seconds"] == current_chapter["start_seconds"]:
            raise WorkflowError(
                f"大纲存在重复章节时间：{format_time(previous['start_seconds'])}"
            )
    return {
        "path": str(path.resolve()),
        "title": title,
        "description": description,
        "chapters": chapters,
        "people": people,
        "term_hints": term_hints,
    }


def apply_corrections(
    blocks: list[dict[str, Any]], rules: list[dict[str, str]]
) -> list[dict[str, Any]]:
    if not rules:
        return []
    by_source = {rule["from"]: rule for rule in rules}
    hits = {rule["from"]: 0 for rule in rules}
    pattern = re.compile(
        "|".join(
            re.escape(source)
            for source in sorted(by_source, key=len, reverse=True)
        )
    )

    def replace(match: re.Match[str]) -> str:
        source = match.group(0)
        hits[source] += 1
        return by_source[source]["to"]

    for block in blocks:
        block["text"] = pattern.sub(replace, block["text"])
    return [{**rule, "hits": hits[rule["from"]]} for rule in rules]


def assign_block_ids(
    blocks: list[dict[str, Any]], speaker_map: dict[str, str]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, source in enumerate(blocks, start=1):
        block = dict(source)
        block["id"] = f"B{index:05d}"
        block["speaker_raw"] = block["speaker"]
        block["speaker"] = speaker_map.get(block["speaker"], block["speaker"])
        block["start"] = format_time(block["start_seconds"])
        block["end"] = format_time(block["end_seconds"])
        result.append(block)
    return result


def next_question_id(items: list[dict[str, Any]]) -> str:
    used = {
        int(match.group(1))
        for item in items
        if (match := re.fullmatch(r"Q(\d+)", str(item.get("id", ""))))
    }
    number = 1
    while number in used:
        number += 1
    return f"Q{number:03d}"


def build_auto_questions(
    blocks: list[dict[str, Any]], outline: dict[str, Any]
) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    unknown_speakers: dict[str, dict[str, Any]] = {}
    for block in blocks:
        raw = block["speaker_raw"]
        if SPEAKER_HINT.fullmatch(raw) and raw == block["speaker"]:
            unknown_speakers.setdefault(raw, block)
    for speaker, block in unknown_speakers.items():
        questions.append(
            {
                "id": next_question_id(questions),
                "target": {"type": "speaker", "speaker": speaker},
                "block_id": block["id"],
                "start": block["start"],
                "speaker": speaker,
                "category": "发言人",
                "original": speaker,
                "suggestion": "",
                "reason": "尚未映射为真实姓名。",
                "confidence": "low",
                "status": "pending",
                "resolution": None,
            }
        )

    seen_terms: dict[tuple[str, str], str] = {}
    for hint in outline["term_hints"]:
        wrong_values = [
            value.strip()
            for value in re.split(r"[、/,，;；]", hint["wrong"])
            if value.strip() and value.strip() != hint["correct"]
        ]
        for wrong in wrong_values:
            for block in blocks:
                if wrong not in block["text"]:
                    continue
                key = (block["id"], wrong)
                previous_suggestion = seen_terms.get(key)
                if previous_suggestion is not None:
                    if previous_suggestion != hint["correct"]:
                        raise WorkflowError(
                            f"大纲术语冲突：{wrong} 同时建议为 "
                            f"{previous_suggestion} 和 {hint['correct']}。"
                        )
                    continue
                seen_terms[key] = hint["correct"]
                questions.append(
                    {
                        "id": next_question_id(questions),
                        "target": {
                            "type": "text",
                            "block_id": block["id"],
                            "original": wrong,
                            "replace_all": True,
                        },
                        "block_id": block["id"],
                        "start": block["start"],
                        "speaker": block["speaker"],
                        "category": "术语",
                        "original": wrong,
                        "suggestion": hint["correct"],
                        "reason": hint["note"] or "大纲术语线索命中。",
                        "confidence": "medium",
                        "status": "pending",
                        "resolution": None,
                    }
                )
    return questions


def paths_for(project: Path, ep_id: str) -> dict[str, Path]:
    return {
        "source_dir": ensure_within(project / "01_raw_docx" / ep_id, project),
        "normalized": ensure_within(
            project / "02_normalized_text" / ep_id / f"{ep_id}.raw.txt", project
        ),
        "review_data": ensure_within(
            project / "03_review_draft" / ep_id / f"{ep_id}.review.json", project
        ),
        "questions": ensure_within(
            project / "03_review_draft" / ep_id / f"{ep_id}.questions.json", project
        ),
        "editor_review": ensure_within(
            project / "03_review_draft" / ep_id / f"{ep_id}.editor-review.md", project
        ),
        "final_text": ensure_within(
            project / "04_final_text" / ep_id / f"{ep_id}.final.md", project
        ),
        "timeline": ensure_within(
            project / "04_final_text" / ep_id / f"{ep_id}.timeline.json", project
        ),
        "chunks": ensure_within(
            project / "05_agent_chunks" / ep_id / f"{ep_id}.chunks.jsonl", project
        ),
        "manifest": ensure_within(project / "manifests" / f"{ep_id}.json", project),
    }


def question_counts(questions: dict[str, Any]) -> tuple[int, int]:
    pending = sum(item.get("status") == "pending" for item in questions["items"])
    resolved = len(questions["items"]) - pending
    return pending, resolved


def derive_status(questions: dict[str, Any], finalized: bool = False) -> str:
    if finalized:
        return "finalized"
    if not questions["agent_review"]["completed"]:
        return "needs_agent_review"
    pending, _ = question_counts(questions)
    return "awaiting_editor" if pending else "ready_to_finalize"


def make_manifest(
    project: Path,
    ep_id: str,
    title: str,
    inputs: dict[str, Any],
    output_paths: dict[str, Path],
    review: dict[str, Any],
    questions: dict[str, Any],
    finalized: bool = False,
    delivery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pending, resolved = question_counts(questions)
    manifest = {
        "schema_version": SCHEMA_MANIFEST,
        "episode_id": ep_id,
        "title": title,
        "status": derive_status(questions, finalized),
        "inputs": inputs,
        "outputs": {
            key: relative_to_project(output_paths[key], project)
            for key in (
                "normalized",
                "review_data",
                "questions",
                "editor_review",
                "final_text",
                "timeline",
                "chunks",
            )
        },
        "counts": {
            "blocks": len(review["blocks"]),
            "chapters": len(review["chapters"]),
            "questions_pending": pending,
            "questions_resolved": resolved,
            "correction_hits": sum(
                item["hits"] for item in review["correction_stats"]
            ),
        },
        "updated_at": now_iso(),
    }
    if finalized:
        if delivery is None:
            raise WorkflowError("生成 finalized manifest 时缺少交付元数据。")
        manifest["delivery"] = delivery
        manifest["delivery_fingerprint"] = json_fingerprint(
            {
                "review": review,
                "questions": questions,
                "chunk_chars": delivery["chunk_chars"],
                "workflow_revision": WORKFLOW_REVISION,
            }
        )
        manifest["finalized_at"] = now_iso()
    return manifest


def chapter_for_block(
    chapters: list[dict[str, Any]], start_seconds: float
) -> dict[str, Any]:
    selected = chapters[0]
    for chapter in chapters:
        if chapter["start_seconds"] <= start_seconds:
            selected = chapter
        else:
            break
    return selected


def markdown_text(value: str) -> str:
    return value.replace("\n", "  \n")


def render_editor_review(
    review: dict[str, Any],
    questions: dict[str, Any],
    finalized: bool = False,
) -> str:
    pending, resolved = question_counts(questions)
    status = derive_status(questions, finalized)
    lines = [
        f"# {review['title']}｜剪辑校对稿",
        "",
        f"> 期号：`{review['episode_id']}`",
        f"> 状态：`{status}`",
        f"> 待确认：{pending} 条；已确认：{resolved} 条",
    ]
    if review["inputs"].get("audio"):
        lines.append(f"> 音频：`{review['inputs']['audio']}`")
    lines.extend(["", "## 给剪辑师", ""])
    if not questions["agent_review"]["completed"]:
        lines.append("⚠️ Agent 尚未完成语义复核，当前稿不应交付剪辑师。")
    elif pending:
        lines.extend(
            [
                "请逐条回听「待确认项」，按以下格式回复即可：",
                "",
                "- `Q001 接受`：采用建议写法",
                "- `Q002 保留`：保留原文",
                "- `Q003 改为：正确内容`：使用你提供的写法",
                "- `Q004 删除`：删除标记文字",
            ]
        )
    else:
        lines.append("✅ 当前没有未解决疑点，可以生成最终稿。")

    if review.get("description"):
        lines.extend(["", "## 节目介绍", "", review["description"]])

    lines.extend(["", "## 时间轴", ""])
    for chapter in review["chapters"]:
        lines.append(f"- {chapter['start']} {chapter['title']}")

    lines.extend(["", "## 待确认项", ""])
    if not questions["items"]:
        lines.append("暂无自动发现的疑点；仍需 Agent 完成语义复核。")
    for item in questions["items"]:
        state = "待确认" if item["status"] == "pending" else "已处理"
        lines.extend(
            [
                f"### {item['id']} · {item['category']} · "
                f"[{item.get('start') or '--:--:--'}] {item.get('speaker', '')}",
                "",
                f"- 状态：{state}",
                f"- 原文：{item.get('original') or '（整段判断）'}",
                f"- 建议：{item.get('suggestion') or '请回听确认'}",
                f"- 原因：{item.get('reason') or '语义不确定'}",
            ]
        )
        if item.get("resolution"):
            resolution = item["resolution"]
            lines.append(
                f"- 处理：{resolution['action']}"
                + (f" → {resolution.get('text', '')}" if resolution.get("text") else "")
            )
        lines.append("")

    lines.extend(["## 正文", ""])
    display_blocks = apply_resolutions(review, questions)
    current_chapter = None
    for block in display_blocks:
        chapter = chapter_for_block(review["chapters"], block["start_seconds"])
        if chapter["id"] != current_chapter:
            lines.extend(
                [
                    f"### [{chapter['start']}] {chapter['title']}",
                    "",
                ]
            )
            current_chapter = chapter["id"]
        lines.extend(
            [
                f"**{block['speaker']}** [{block['start']}]："
                f"{markdown_text(block['text'])}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def load_episode(
    project: Path, ep_id: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Path]]:
    output_paths = paths_for(project, ep_id)
    review = load_json(output_paths["review_data"], "初校结构化数据")
    questions = load_json(output_paths["questions"], "疑点数据")
    if review.get("schema_version") != SCHEMA_REVIEW:
        raise WorkflowError("初校数据版本不受支持。")
    if questions.get("schema_version") != SCHEMA_QUESTIONS:
        raise WorkflowError("疑点数据版本不受支持。")
    return review, questions, output_paths


def update_episode_files(
    project: Path,
    review: dict[str, Any],
    questions: dict[str, Any],
    output_paths: dict[str, Path],
    finalized: bool = False,
    delivery: dict[str, Any] | None = None,
) -> None:
    editor_markdown = render_editor_review(
        review, questions, finalized=finalized
    )
    manifest = make_manifest(
        project=project,
        ep_id=review["episode_id"],
        title=review["title"],
        inputs=review["inputs"],
        output_paths=output_paths,
        review=review,
        questions=questions,
        finalized=finalized,
        delivery=delivery,
    )
    atomic_write_json(output_paths["review_data"], review)
    atomic_write_json(output_paths["questions"], questions)
    atomic_write_text(output_paths["editor_review"], editor_markdown)
    atomic_write_json(output_paths["manifest"], manifest)


def archive_stale_outputs(output_paths: dict[str, Path]) -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archived = 0
    for key in ("final_text", "timeline", "chunks"):
        path = output_paths[key]
        if not path.is_file():
            continue
        archive_dir = path.parent / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        destination = archive_dir / f"{path.stem}.{stamp}{path.suffix}"
        counter = 1
        while destination.exists():
            destination = (
                archive_dir / f"{path.stem}.{stamp}.{counter}{path.suffix}"
            )
            counter += 1
        os.replace(path, destination)
        archived += 1
    return archived


def validate_timing(
    blocks: list[dict[str, Any]],
    chapters: list[dict[str, Any]],
    duration_seconds: float | None,
) -> None:
    previous_start = -1.0
    max_timestamp = 0.0
    for block in blocks:
        start = float(block["start_seconds"])
        end = block.get("end_seconds")
        if start < previous_start:
            raise WorkflowError(
                f"转写时间戳不是升序：{format_time(start)} 出现在 "
                f"{format_time(previous_start)} 之后。"
            )
        if end is not None and float(end) < start:
            raise WorkflowError(
                f"转写时间范围反向：{format_time(start)} → {format_time(end)}。"
            )
        previous_start = start
        max_timestamp = max(
            max_timestamp, start, float(end) if end is not None else 0.0
        )
    if chapters:
        max_timestamp = max(
            max_timestamp,
            max(float(chapter["start_seconds"]) for chapter in chapters),
        )
    if duration_seconds is not None and duration_seconds < max_timestamp:
        raise WorkflowError(
            f"节目总时长 {format_time(duration_seconds)} 早于正文或章节的最后时间 "
            f"{format_time(max_timestamp)}。"
        )


def command_init(args: argparse.Namespace) -> None:
    project = Path(args.project).expanduser().resolve()
    project.mkdir(parents=True, exist_ok=True)
    for directory in PROJECT_DIRS:
        (project / directory).mkdir(parents=True, exist_ok=True)

    repo_root = Path(__file__).resolve().parent.parent
    templates = {
        repo_root / "template" / "corrections_empty.json": project
        / "corrections.json",
        repo_root / "template" / "sample_outline.md": project
        / "outlines"
        / "sample_outline.md",
        repo_root / "template" / "glossary_template.md": project
        / "glossary"
        / "README.md",
    }
    created: list[str] = []
    skipped: list[str] = []
    for source, destination in templates.items():
        if destination.exists():
            skipped.append(relative_to_project(destination, project))
        elif source.is_file():
            shutil.copy2(source, destination)
            created.append(relative_to_project(destination, project))
        else:
            raise WorkflowError(f"Skill 安装不完整，缺少模板：{source}")
    speaker_map = project / "speaker_map.json"
    if speaker_map.exists():
        skipped.append("speaker_map.json")
    else:
        atomic_write_json(speaker_map, {})
        created.append("speaker_map.json")

    print(f"✅ 项目已就绪：{project}")
    if created:
        print("新建：" + "、".join(created))
    if skipped:
        print("保留已有文件：" + "、".join(skipped))
    print("下一步：把转写稿放入 00_inbox/，并运行 prepare。")


def command_prepare(args: argparse.Namespace) -> None:
    project = Path(args.project).expanduser().resolve()
    if not project.is_dir():
        raise WorkflowError(f"项目目录不存在，请先运行 init：{project}")
    source = Path(args.input).expanduser().resolve()
    if not source.is_file():
        raise WorkflowError(f"转写稿不存在：{source}")
    ep_id = validate_episode_id(args.ep_id or derive_episode_id(source))
    output_paths = paths_for(project, ep_id)

    outline_path = Path(args.outline).expanduser().resolve() if args.outline else None
    speaker_map_path = (
        Path(args.speaker_map).expanduser().resolve()
        if args.speaker_map
        else (project / "speaker_map.json" if (project / "speaker_map.json").is_file() else None)
    )
    corrections_path = (
        Path(args.corrections).expanduser().resolve()
        if args.corrections
        else (project / "corrections.json" if (project / "corrections.json").is_file() else None)
    )
    audio_path = Path(args.audio).expanduser().resolve() if args.audio else None
    if audio_path is not None and not audio_path.is_file():
        raise WorkflowError(f"音频文件不存在：{audio_path}")

    input_hashes = {
        "transcript": file_sha256(source),
        "outline": file_sha256(outline_path) if outline_path else "",
        "speaker_map": file_sha256(speaker_map_path) if speaker_map_path else "",
        "corrections": file_sha256(corrections_path) if corrections_path else "",
    }
    prepare_fingerprint = json_fingerprint(
        {
            "workflow_revision": WORKFLOW_REVISION,
            "sha256": input_hashes,
            "title": args.title or "",
            "duration": args.duration or "",
            "audio": str(audio_path) if audio_path else "",
        }
    )
    if output_paths["manifest"].is_file() and not args.force:
        existing = load_json(output_paths["manifest"], "Manifest")
        required_outputs = (
            output_paths["normalized"],
            output_paths["review_data"],
            output_paths["questions"],
            output_paths["editor_review"],
        )
        if (
            existing.get("inputs", {}).get("prepare_fingerprint")
            == prepare_fingerprint
            and all(path.is_file() for path in required_outputs)
        ):
            print(f"✅ {ep_id} 已按相同输入准备完成，无需重复执行。")
            print(f"剪辑校对稿：{output_paths['editor_review']}")
            return
        if (
            existing.get("inputs", {}).get("prepare_fingerprint")
            != prepare_fingerprint
        ):
            raise WorkflowError(
                f"{ep_id} 已存在且输入不同；如确认重建，请加 --force。"
            )
    raw_text = extract_source_text(source)
    speaker_map = load_speaker_map(speaker_map_path)
    known_speakers = set(speaker_map) | set(speaker_map.values())
    if source.suffix.lower() in {".srt", ".vtt"}:
        parsed = parse_subtitle(raw_text, known_speakers)
        parse_info = {"mode": "subtitle", "preamble_lines": 0}
    else:
        parsed, parse_info = parse_plain_transcript(raw_text, known_speakers)
    if not parsed:
        raise WorkflowError("没有识别出任何正文块，请检查转写格式。")

    blocks = assign_block_ids(parsed, speaker_map)
    corrections = load_corrections(corrections_path)
    correction_stats = apply_corrections(blocks, corrections)
    outline = parse_outline(outline_path)
    chapters = outline["chapters"] or [{"start_seconds": 0, "title": "全文"}]
    if chapters[0]["start_seconds"] > 0:
        chapters.insert(0, {"start_seconds": 0, "title": "开场"})
    for index, chapter in enumerate(chapters, start=1):
        chapter["id"] = f"C{index:03d}"
        chapter["start"] = format_time(chapter["start_seconds"])
    title = args.title or outline["title"] or source.stem
    duration_seconds = parse_time(args.duration) if args.duration else None
    if duration_seconds is None and blocks[-1]["end_seconds"] is not None:
        duration_seconds = blocks[-1]["end_seconds"]
    validate_timing(blocks, chapters, duration_seconds)

    archived_source = output_paths["source_dir"] / source.name
    if (
        archived_source.exists()
        and file_sha256(archived_source) != input_hashes["transcript"]
    ):
        archived_source = archived_source.with_name(
            f"{archived_source.stem}.{input_hashes['transcript'][:8]}"
            f"{archived_source.suffix}"
        )

    inputs = {
        "transcript": relative_to_project(source, project),
        "archived_transcript": relative_to_project(archived_source, project),
        "outline": relative_to_project(outline_path, project),
        "audio": relative_to_project(audio_path, project),
        "speaker_map": relative_to_project(speaker_map_path, project),
        "corrections": relative_to_project(corrections_path, project),
        "sha256": input_hashes,
        "prepare_fingerprint": prepare_fingerprint,
    }
    review = {
        "schema_version": SCHEMA_REVIEW,
        "episode_id": ep_id,
        "title": title,
        "description": outline["description"],
        "people": outline["people"],
        "duration_seconds": duration_seconds,
        "duration": format_time(duration_seconds),
        "inputs": inputs,
        "parse": parse_info,
        "chapters": chapters,
        "term_hints": outline["term_hints"],
        "correction_stats": correction_stats,
        "agent_edits": [],
        "blocks": blocks,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    questions = {
        "schema_version": SCHEMA_QUESTIONS,
        "episode_id": ep_id,
        "agent_review": {
            "completed": False,
            "completed_at": None,
            "notes": "",
        },
        "items": build_auto_questions(blocks, outline),
        "updated_at": now_iso(),
    }
    if args.force:
        archived_count = archive_stale_outputs(output_paths)
        if archived_count:
            print(f"已归档旧最终交付：{archived_count} 个文件。")
    archived_source.parent.mkdir(parents=True, exist_ok=True)
    if not archived_source.exists():
        shutil.copy2(source, archived_source)
    atomic_write_text(output_paths["normalized"], raw_text)
    update_episode_files(project, review, questions, output_paths)

    pending, _ = question_counts(questions)
    print(f"✅ 已准备 {ep_id}：{len(blocks)} 段，{len(chapters)} 章。")
    print(f"自动疑点：{pending} 条；下一步由 Agent 执行语义复核。")
    print(f"结构化初校：{output_paths['review_data']}")
    print(f"疑点数据：{output_paths['questions']}")
    print(f"剪辑校对稿：{output_paths['editor_review']}")


def command_agent_review(args: argparse.Namespace) -> None:
    project = Path(args.project).expanduser().resolve()
    ep_id = validate_episode_id(args.ep_id)
    review, questions, output_paths = load_episode(project, ep_id)
    manifest = load_json(output_paths["manifest"], "Manifest")
    if manifest.get("status") != "needs_agent_review":
        raise WorkflowError(
            f"当前状态是 {manifest.get('status')}，不能执行 agent-review。"
        )
    payload_path = Path(args.input).expanduser().resolve()
    if not payload_path.is_file():
        raise WorkflowError(f"Agent 复核结果不存在：{payload_path}")
    payload_hash = file_sha256(payload_path)
    if questions["agent_review"]["completed"]:
        if questions["agent_review"].get("input_sha256") == payload_hash:
            print(f"✅ {ep_id} 已登记相同的 Agent 复核结果，无需重复执行。")
            return
        raise WorkflowError(
            "Agent 语义复核已经完成；如需重做，请重新 prepare --force。"
        )
    payload = load_json(payload_path, "Agent 复核结果")
    if not isinstance(payload, dict):
        raise WorkflowError("Agent 复核结果必须是 JSON 对象。")
    if not {"edits", "questions"}.issubset(payload):
        raise WorkflowError("Agent 复核结果必须显式包含 edits 和 questions。")
    unknown_keys = set(payload) - {"edits", "questions", "notes"}
    if unknown_keys:
        raise WorkflowError(
            "Agent 复核结果包含未知字段：" + "、".join(sorted(unknown_keys))
        )
    edits = payload["edits"]
    new_questions = payload["questions"]
    if not isinstance(edits, list) or not isinstance(new_questions, list):
        raise WorkflowError("Agent 复核结果的 edits/questions 必须是数组。")
    block_map = {block["id"]: block for block in review["blocks"]}
    existing_targets = {
        (
            item.get("target", {}).get("type"),
            item.get("target", {}).get("block_id")
            or item.get("target", {}).get("speaker"),
            item.get("target", {}).get("original", ""),
        )
        for item in questions["items"]
    }

    for index, edit in enumerate(edits, start=1):
        if not isinstance(edit, dict):
            raise WorkflowError(f"Agent edit 第 {index} 项格式错误。")
        block_id = edit.get("block_id")
        original = edit.get("original")
        replacement = edit.get("replacement")
        if block_id not in block_map:
            raise WorkflowError(f"Agent edit 指向不存在的 block：{block_id}")
        if not isinstance(original, str) or not isinstance(replacement, str):
            raise WorkflowError(f"Agent edit 第 {index} 项缺少 original/replacement。")
        block = block_map[block_id]
        for pending_item in questions["items"]:
            target = pending_item.get("target", {})
            pending_original = str(target.get("original", ""))
            if (
                target.get("type") == "text"
                and target.get("block_id") == block_id
                and pending_original
                and (
                    pending_original in original
                    or original in pending_original
                )
            ):
                raise WorkflowError(
                    f"Agent edit 第 {index} 项与已有疑点 "
                    f"{pending_item['id']} 重叠。"
                )
        occurrences = block["text"].count(original)
        if occurrences != 1:
            raise WorkflowError(
                f"Agent edit {block_id} 的原文应恰好命中 1 次，实际 {occurrences} 次。"
            )
        block["text"] = block["text"].replace(original, replacement, 1)
        review["agent_edits"].append(
            {
                "block_id": block_id,
                "original": original,
                "replacement": replacement,
                "reason": str(edit.get("reason", "")),
            }
        )

    for index, item in enumerate(new_questions, start=1):
        if not isinstance(item, dict):
            raise WorkflowError(f"Agent question 第 {index} 项格式错误。")
        block_id = item.get("block_id")
        block = block_map.get(block_id) if block_id else None
        target_type = item.get("target_type", "text")
        original = str(item.get("original", ""))
        if target_type not in {"text", "speaker"}:
            raise WorkflowError(
                f"Agent question 第 {index} 项 target_type 只能是 text/speaker。"
            )
        if target_type == "text" and block is None:
            raise WorkflowError(f"Agent question 第 {index} 项缺少有效 block_id。")
        if target_type == "text":
            occurrences = block["text"].count(original) if original else 0
            if occurrences != 1:
                raise WorkflowError(
                    f"Agent question 第 {index} 项 original 在 {block_id} "
                    f"应命中 1 次，实际 {occurrences} 次。"
                )
        elif not any(existing["speaker"] == original for existing in review["blocks"]):
            raise WorkflowError(
                f"Agent question 第 {index} 项引用了不存在的发言人：{original}"
            )
        target = (
            {"type": "text", "block_id": block_id, "original": original}
            if target_type == "text"
            else {"type": "speaker", "speaker": original}
        )
        target_key = (
            target["type"],
            target.get("block_id") or target.get("speaker"),
            target.get("original", ""),
        )
        if target_key in existing_targets:
            raise WorkflowError(
                f"Agent question 第 {index} 项与已有疑点重复。"
            )
        existing_targets.add(target_key)
        questions["items"].append(
            {
                "id": next_question_id(questions["items"]),
                "target": target,
                "block_id": block_id or "",
                "start": block["start"] if block else str(item.get("start", "")),
                "speaker": block["speaker"] if block else original,
                "category": str(item.get("category", "语义")),
                "original": original,
                "suggestion": str(item.get("suggestion", "")),
                "reason": str(item.get("reason", "")),
                "confidence": str(item.get("confidence", "low")),
                "status": "pending",
                "resolution": None,
            }
        )

    questions["agent_review"] = {
        "completed": True,
        "completed_at": now_iso(),
        "notes": str(payload.get("notes", "")),
        "input_sha256": payload_hash,
    }
    questions["updated_at"] = now_iso()
    review["updated_at"] = now_iso()
    update_episode_files(project, review, questions, output_paths)
    pending, _ = question_counts(questions)
    print(f"✅ Agent 语义复核已登记：{len(edits)} 处确定修改，{pending} 条待确认。")
    print(f"可交付剪辑师：{output_paths['editor_review']}")


def normalize_answers(data: Any) -> dict[str, dict[str, str]]:
    if isinstance(data, dict) and "answers" in data:
        data = data["answers"]
    if isinstance(data, dict):
        result = {}
        for question_id, answer in data.items():
            if isinstance(answer, str):
                result[str(question_id)] = {"action": answer}
            elif isinstance(answer, dict):
                result[str(question_id)] = {
                    "action": str(answer.get("action", "")),
                    "text": str(answer.get("text", "")),
                }
            else:
                raise WorkflowError(f"疑点 {question_id} 的答复格式错误。")
        return result
    if isinstance(data, list):
        result = {}
        for item in data:
            if not isinstance(item, dict) or not item.get("id"):
                raise WorkflowError("answers 数组每项必须包含 id。")
            result[str(item["id"])] = {
                "action": str(item.get("action", "")),
                "text": str(item.get("text", "")),
            }
        return result
    raise WorkflowError("答复必须是对象，或包含 answers 的对象。")


def command_resolve(args: argparse.Namespace) -> None:
    project = Path(args.project).expanduser().resolve()
    ep_id = validate_episode_id(args.ep_id)
    review, questions, output_paths = load_episode(project, ep_id)
    manifest = load_json(output_paths["manifest"], "Manifest")
    if manifest.get("status") == "finalized":
        raise WorkflowError("本期已经 finalized；如需修改，请重新 prepare --force。")
    if not questions["agent_review"]["completed"]:
        raise WorkflowError("Agent 尚未完成语义复核，不能登记剪辑师答复。")
    answers = normalize_answers(
        load_json(Path(args.answers).expanduser().resolve(), "剪辑师答复")
    )
    item_map = {item["id"]: item for item in questions["items"]}
    allowed = {"accept", "keep", "replace", "remove"}
    for question_id, answer in answers.items():
        if question_id not in item_map:
            raise WorkflowError(f"答复引用了不存在的疑点：{question_id}")
        action = answer.get("action", "").lower()
        aliases = {
            "接受": "accept",
            "保留": "keep",
            "改为": "replace",
            "删除": "remove",
        }
        action = aliases.get(action, action)
        if action not in allowed:
            raise WorkflowError(
                f"{question_id} action 应为 accept/keep/replace/remove。"
            )
        item = item_map[question_id]
        if action == "accept" and not item.get("suggestion"):
            raise WorkflowError(f"{question_id} 没有建议值，不能 accept。")
        if action == "replace" and not answer.get("text"):
            raise WorkflowError(f"{question_id} 使用 replace 时必须提供 text。")
        item["status"] = "resolved"
        item["resolution"] = {
            "action": action,
            "text": answer.get("text", ""),
            "resolved_at": now_iso(),
        }
    questions["updated_at"] = now_iso()
    update_episode_files(project, review, questions, output_paths)
    pending, resolved = question_counts(questions)
    print(f"✅ 已登记答复：待确认 {pending} 条，已处理 {resolved} 条。")
    if pending == 0:
        print(f"下一步：finalize --project {project} --ep-id {ep_id}")


def apply_resolutions(
    review: dict[str, Any], questions: dict[str, Any]
) -> list[dict[str, Any]]:
    blocks = copy.deepcopy(review["blocks"])
    block_map = {block["id"]: block for block in blocks}
    for item in questions["items"]:
        resolution = item.get("resolution") or {}
        action = resolution.get("action")
        if action not in {"accept", "keep", "replace", "remove"}:
            continue
        if action == "keep":
            continue
        replacement = (
            item.get("suggestion", "")
            if action == "accept"
            else resolution.get("text", "")
            if action == "replace"
            else ""
        )
        target = item.get("target", {})
        if target.get("type") == "speaker":
            original_speaker = target.get("speaker")
            for block in blocks:
                if block["speaker"] == original_speaker:
                    block["speaker"] = replacement
            continue
        block_id = target.get("block_id") or item.get("block_id")
        original = target.get("original", item.get("original", ""))
        if action == "keep" or not original:
            continue
        block = block_map.get(block_id)
        if block is None:
            raise WorkflowError(f"{item['id']} 指向不存在的 block：{block_id}")
        occurrences = block["text"].count(original)
        replace_all = bool(target.get("replace_all"))
        if occurrences < 1 or (not replace_all and occurrences != 1):
            raise WorkflowError(
                f"{item['id']} 的原文在 {block_id} 命中次数异常：{occurrences}。"
            )
        block["text"] = block["text"].replace(
            original, replacement, -1 if replace_all else 1
        )
    return blocks


def build_timeline(
    review: dict[str, Any], blocks: list[dict[str, Any]]
) -> dict[str, Any]:
    chapters = copy.deepcopy(review["chapters"])
    duration = review.get("duration_seconds")
    for index, chapter in enumerate(chapters):
        end_seconds = (
            chapters[index + 1]["start_seconds"]
            if index + 1 < len(chapters)
            else duration
        )
        chapter_blocks = [
            block
            for block in blocks
            if block["start_seconds"] >= chapter["start_seconds"]
            and (end_seconds is None or block["start_seconds"] < end_seconds)
        ]
        chapter["end_seconds"] = end_seconds
        chapter["end"] = format_time(end_seconds)
        chapter["block_count"] = len(chapter_blocks)
        chapter["speakers"] = list(
            dict.fromkeys(block["speaker"] for block in chapter_blocks)
        )
    return {
        "schema_version": SCHEMA_TIMELINE,
        "episode_id": review["episode_id"],
        "title": review["title"],
        "duration_seconds": duration,
        "duration": format_time(duration),
        "chapters": chapters,
        "generated_at": now_iso(),
    }


def render_final_markdown(
    review: dict[str, Any],
    blocks: list[dict[str, Any]],
    timeline: dict[str, Any],
) -> str:
    lines = [
        f"# {review['title']}",
        "",
        f"> 期号：`{review['episode_id']}`",
        f"> 时长：{review.get('duration') or '未知'}",
    ]
    if review.get("description"):
        lines.extend(["", "## 节目介绍", "", review["description"]])
    lines.extend(["", "## 时间轴", ""])
    for chapter in timeline["chapters"]:
        end = f"–{chapter['end']}" if chapter.get("end") else ""
        lines.append(f"- [{chapter['start']}{end}] {chapter['title']}")
    lines.extend(["", "## 文字稿", ""])
    current_chapter = None
    for block in blocks:
        chapter = chapter_for_block(review["chapters"], block["start_seconds"])
        if chapter["id"] != current_chapter:
            lines.extend(
                ["", f"### [{chapter['start']}] {chapter['title']}", ""]
            )
            current_chapter = chapter["id"]
        lines.extend(
            [
                f"**{block['speaker']}** [{block['start']}]："
                f"{markdown_text(block['text'])}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def split_text_for_chunks(text: str, max_chars: int) -> list[str]:
    """Split long turns without losing text, preferring sentence boundaries."""
    if len(text) <= max_chars:
        return [text]
    pieces = [
        piece.strip()
        for piece in re.split(r"(?<=[。！？!?；;\n])", text)
        if piece.strip()
    ]
    segments: list[str] = []
    current = ""
    for piece in pieces:
        while len(piece) > max_chars:
            if current:
                segments.append(current)
                current = ""
            segments.append(piece[:max_chars])
            piece = piece[max_chars:]
        if not piece:
            continue
        if current and len(current) + len(piece) > max_chars:
            segments.append(current)
            current = piece
        else:
            current += piece
    if current:
        segments.append(current)
    if segments:
        return segments
    return [
        text[index : index + max_chars]
        for index in range(0, len(text), max_chars)
    ]


def build_chunks(
    review: dict[str, Any],
    blocks: list[dict[str, Any]],
    timeline: dict[str, Any],
    max_chars: int,
) -> list[dict[str, Any]]:
    timeline_by_id = {chapter["id"]: chapter for chapter in timeline["chapters"]}
    grouped: dict[str, list[dict[str, Any]]] = {
        chapter["id"]: [] for chapter in review["chapters"]
    }
    for block in blocks:
        chapter = chapter_for_block(review["chapters"], block["start_seconds"])
        grouped[chapter["id"]].append(block)

    chunks: list[dict[str, Any]] = []
    for chapter in review["chapters"]:
        chapter_blocks = grouped[chapter["id"]]
        units: list[dict[str, Any]] = []
        text_limit = max(80, max_chars - 64)
        for block in chapter_blocks:
            segments = split_text_for_chunks(block["text"], text_limit)
            for segment_index, segment in enumerate(segments, start=1):
                unit = dict(block)
                unit["text"] = segment
                unit["segment_index"] = segment_index
                unit["segment_count"] = len(segments)
                units.append(unit)

        batches: list[tuple[list[dict[str, Any]], bool]] = []
        current: list[dict[str, Any]] = []
        current_length = 0
        overlaps_previous = False
        for block in units:
            rendered = f"{block['speaker']}：{block['text']}"
            if current and current_length + len(rendered) > max_chars:
                batches.append((current, overlaps_previous))
                overlap = current[-1]
                overlap_length = len(f"{overlap['speaker']}：{overlap['text']}")
                if overlap_length <= max_chars // 3:
                    current = [overlap]
                    current_length = overlap_length
                    overlaps_previous = True
                else:
                    current = []
                    current_length = 0
                    overlaps_previous = False
                if current and current_length + len(rendered) > max_chars:
                    current = []
                    current_length = 0
                    overlaps_previous = False
            current.append(block)
            current_length += len(rendered)
        if current:
            batches.append((current, overlaps_previous))

        for batch_index, (batch, overlaps_previous) in enumerate(
            batches, start=1
        ):
            start_seconds = batch[0]["start_seconds"]
            end_seconds = batch[-1].get("end_seconds")
            if end_seconds is None:
                end_seconds = timeline_by_id[chapter["id"]].get("end_seconds")
            chunks.append(
                {
                    "schema_version": SCHEMA_CHUNK,
                    "id": (
                        f"{review['episode_id']}-{chapter['id'].lower()}-"
                        f"{batch_index:03d}"
                    ),
                    "episode_id": review["episode_id"],
                    "episode_title": review["title"],
                    "source_sha256": review["inputs"]["sha256"]["transcript"],
                    "chapter_id": chapter["id"],
                    "chapter_title": chapter["title"],
                    "start_seconds": start_seconds,
                    "start": format_time(start_seconds),
                    "end_seconds": end_seconds,
                    "end": format_time(end_seconds),
                    "speakers": list(
                        dict.fromkeys(block["speaker"] for block in batch)
                    ),
                    "block_ids": list(
                        dict.fromkeys(block["id"] for block in batch)
                    ),
                    "overlaps_previous": overlaps_previous,
                    "turns": [
                        {
                            "block_id": block["id"],
                            "speaker": block["speaker"],
                            "start": block["start"],
                            "end": block["end"],
                            "segment_index": block["segment_index"],
                            "segment_count": block["segment_count"],
                            "text": block["text"],
                        }
                        for block in batch
                    ],
                    "text": "\n".join(
                        f"{block['speaker']}：{block['text']}" for block in batch
                    ),
                    "char_count": sum(len(block["text"]) for block in batch),
                }
            )
    return chunks


def command_finalize(args: argparse.Namespace) -> None:
    project = Path(args.project).expanduser().resolve()
    ep_id = validate_episode_id(args.ep_id)
    review, questions, output_paths = load_episode(project, ep_id)
    manifest = load_json(output_paths["manifest"], "Manifest")
    if not questions["agent_review"]["completed"]:
        raise WorkflowError("Agent 尚未完成语义复核，不能生成最终稿。")
    pending, _ = question_counts(questions)
    if pending:
        raise WorkflowError(f"仍有 {pending} 条待确认疑点，不能生成最终稿。")
    final_outputs = (
        output_paths["final_text"],
        output_paths["timeline"],
        output_paths["chunks"],
    )
    delivery_fingerprint = json_fingerprint(
        {
            "review": review,
            "questions": questions,
            "chunk_chars": args.chunk_chars,
            "workflow_revision": WORKFLOW_REVISION,
        }
    )
    if any(path.exists() for path in final_outputs) and not args.force:
        expected_hashes = manifest.get("delivery", {}).get("output_sha256", {})
        outputs_match = all(
            expected_hashes.get(key) == file_sha256(output_paths[key])
            for key in ("final_text", "timeline", "chunks")
            if output_paths[key].is_file()
        ) and len(expected_hashes) == 3
        if (
            all(path.exists() for path in final_outputs)
            and manifest.get("status") == "finalized"
            and manifest.get("delivery_fingerprint") == delivery_fingerprint
            and outputs_match
        ):
            print(f"✅ 最终交付已存在：{output_paths['final_text']}")
            return
        if manifest.get("status") == "finalized":
            raise WorkflowError("最终交付不完整或指纹不一致，请使用 --force 重建。")
    blocks = apply_resolutions(review, questions)
    timeline = build_timeline(review, blocks)
    final_markdown = render_final_markdown(review, blocks, timeline)
    chunks = build_chunks(review, blocks, timeline, args.chunk_chars)
    atomic_write_text(output_paths["final_text"], final_markdown)
    atomic_write_json(output_paths["timeline"], timeline)
    atomic_write_text(
        output_paths["chunks"],
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in chunks),
    )
    delivery = {
        "chunk_chars": args.chunk_chars,
        "workflow_revision": WORKFLOW_REVISION,
        "output_sha256": {
            key: file_sha256(output_paths[key])
            for key in ("final_text", "timeline", "chunks")
        },
    }
    update_episode_files(
        project,
        review,
        questions,
        output_paths,
        finalized=True,
        delivery=delivery,
    )
    print(f"✅ 最终交付已生成：{ep_id}")
    print(f"最终文字稿：{output_paths['final_text']}")
    print(f"结构化时间轴：{output_paths['timeline']}")
    print(f"检索切片：{output_paths['chunks']}（{len(chunks)} 条）")


def command_render(args: argparse.Namespace) -> None:
    project = Path(args.project).expanduser().resolve()
    ep_id = validate_episode_id(args.ep_id)
    review, questions, output_paths = load_episode(project, ep_id)
    manifest = load_json(output_paths["manifest"], "Manifest")
    delivery = manifest.get("delivery", {})
    delivery_fingerprint = json_fingerprint(
        {
            "review": review,
            "questions": questions,
            "chunk_chars": delivery.get("chunk_chars"),
            "workflow_revision": WORKFLOW_REVISION,
        }
    )
    expected_hashes = delivery.get("output_sha256", {})
    outputs_match = all(
        output_paths[key].is_file()
        and expected_hashes.get(key) == file_sha256(output_paths[key])
        for key in ("final_text", "timeline", "chunks")
    )
    finalized = (
        manifest.get("status") == "finalized"
        and manifest.get("delivery_fingerprint") == delivery_fingerprint
        and outputs_match
    )
    update_episode_files(
        project,
        review,
        questions,
        output_paths,
        finalized=finalized,
        delivery=delivery if finalized else None,
    )
    print(f"✅ 已刷新剪辑校对稿：{output_paths['editor_review']}")


def command_status(args: argparse.Namespace) -> None:
    project = Path(args.project).expanduser().resolve()
    manifests = (
        [paths_for(project, validate_episode_id(args.ep_id))["manifest"]]
        if args.ep_id
        else sorted((project / "manifests").glob("*.json"))
    )
    if not manifests:
        print("暂无节目记录。")
        return
    if args.ep_id and not manifests[0].is_file():
        raise WorkflowError(f"找不到期号 {args.ep_id} 的状态记录。")
    data = [load_json(path, "Manifest") for path in manifests if path.is_file()]
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    for manifest in data:
        counts = manifest.get("counts", {})
        next_steps = {
            "needs_agent_review": "下一步 agent-review",
            "awaiting_editor": "下一步 resolve",
            "ready_to_finalize": "下一步 finalize",
            "finalized": "已完成",
        }
        print(
            f"{manifest['episode_id']}: {manifest['status']} · "
            f"{counts.get('blocks', 0)} 段 · "
            f"{counts.get('questions_pending', 0)} 条待确认 · "
            f"{next_steps.get(manifest['status'], '请检查状态')}"
        )


def command_doctor(_: argparse.Namespace) -> None:
    print(f"Python：{sys.version.split()[0]}")
    if sys.version_info < (3, 10):
        raise WorkflowError("需要 Python 3.10 或更高版本。")
    print("DOCX：内置解析，无需安装 python-docx")
    print("✅ 运行环境可用。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Agent-friendly podcast transcript proofreading workflow"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="安全初始化项目目录")
    init_parser.add_argument("--project", required=True, help="项目目录")
    init_parser.set_defaults(func=command_init)

    prepare_parser = subparsers.add_parser(
        "prepare", help="导入并生成结构化初校和剪辑校对稿"
    )
    prepare_parser.add_argument("--project", required=True, help="项目目录")
    prepare_parser.add_argument("--input", required=True, help="转写稿文件")
    prepare_parser.add_argument("--outline", help="节目大纲 Markdown")
    prepare_parser.add_argument("--audio", help="供剪辑师回听的音频文件")
    prepare_parser.add_argument("--ep-id", help="期号；默认从文件名推导")
    prepare_parser.add_argument("--title", help="节目标题；默认读取大纲 H1")
    prepare_parser.add_argument(
        "--speaker-map", help="发言人映射 JSON；默认使用项目 speaker_map.json"
    )
    prepare_parser.add_argument(
        "--corrections", help="纠错规则 JSON；默认使用项目 corrections.json"
    )
    prepare_parser.add_argument("--duration", help="节目总时长，如 01:20:30")
    prepare_parser.add_argument(
        "--force", action="store_true", help="确认重建已有初校数据"
    )
    prepare_parser.set_defaults(func=command_prepare)

    agent_parser = subparsers.add_parser(
        "agent-review", help="登记 Agent 的确定修改与语义疑点"
    )
    agent_parser.add_argument("--project", required=True)
    agent_parser.add_argument("--ep-id", required=True)
    agent_parser.add_argument("--input", required=True, help="Agent 复核结果 JSON")
    agent_parser.set_defaults(func=command_agent_review)

    resolve_parser = subparsers.add_parser(
        "resolve", help="登记剪辑师对疑点的确认结果"
    )
    resolve_parser.add_argument("--project", required=True)
    resolve_parser.add_argument("--ep-id", required=True)
    resolve_parser.add_argument("--answers", required=True, help="答复 JSON")
    resolve_parser.set_defaults(func=command_resolve)

    finalize_parser = subparsers.add_parser(
        "finalize", help="生成最终文字稿、时间轴和检索切片"
    )
    finalize_parser.add_argument("--project", required=True)
    finalize_parser.add_argument("--ep-id", required=True)
    finalize_parser.add_argument(
        "--chunk-chars",
        type=int,
        default=1800,
        help="检索切片目标字符数，默认 1800",
    )
    finalize_parser.add_argument(
        "--force", action="store_true", help="重新生成已有最终交付"
    )
    finalize_parser.set_defaults(func=command_finalize)

    render_parser = subparsers.add_parser("render", help="刷新剪辑校对 Markdown")
    render_parser.add_argument("--project", required=True)
    render_parser.add_argument("--ep-id", required=True)
    render_parser.set_defaults(func=command_render)

    status_parser = subparsers.add_parser("status", help="查看处理状态和下一阶段")
    status_parser.add_argument("--project", required=True)
    status_parser.add_argument("--ep-id")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=command_status)

    doctor_parser = subparsers.add_parser("doctor", help="检查运行环境")
    doctor_parser.set_defaults(func=command_doctor)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if getattr(args, "chunk_chars", 1800) < 200:
            raise WorkflowError("--chunk-chars 不能小于 200。")
        args.func(args)
        return 0
    except WorkflowError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("❌ 已取消。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
