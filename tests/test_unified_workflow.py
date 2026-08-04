"""End-to-end tests for the agent-friendly proofreading workflow."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "scripts" / "podcast_proofreader.py"
DEMO = REPO_ROOT / "examples" / "demo"


class WorkflowTestCase(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.project = self.workspace / "project"
        self.transcript = self.workspace / "transcript.txt"
        shutil.copy2(DEMO / "transcript.txt", self.transcript)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(
        self, *arguments: object, expected_returncode: int = 0
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(CLI), *(str(value) for value in arguments)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != expected_returncode:
            self.fail(
                "CLI 返回码不符。\n"
                f"命令参数：{arguments!r}\n"
                f"期望：{expected_returncode}，实际：{result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        return result

    def write_json(self, path: Path, data: object) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def load_json(self, path: Path) -> object:
        return json.loads(path.read_text(encoding="utf-8"))

    def init_project(self) -> None:
        self.run_cli("init", "--project", self.project)

    def prepare(self, *, force: bool = False) -> subprocess.CompletedProcess[str]:
        arguments: list[object] = [
            "prepare",
            "--project",
            self.project,
            "--input",
            self.transcript,
            "--outline",
            DEMO / "outline.md",
            "--speaker-map",
            DEMO / "speaker_map.json",
            "--corrections",
            DEMO / "corrections.json",
            "--ep-id",
            "ep001",
        ]
        if force:
            arguments.append("--force")
        return self.run_cli(*arguments)

    def agent_review(self) -> None:
        self.run_cli(
            "agent-review",
            "--project",
            self.project,
            "--ep-id",
            "ep001",
            "--input",
            DEMO / "agent_review.json",
        )

    def resolve_all(self) -> None:
        self.run_cli(
            "resolve",
            "--project",
            self.project,
            "--ep-id",
            "ep001",
            "--answers",
            DEMO / "answers.json",
        )

    def episode_path(self, area: str, suffix: str) -> Path:
        return self.project / area / "ep001" / f"ep001.{suffix}"

    def test_init_preserves_existing_user_files(self) -> None:
        existing = {
            self.project / "corrections.json": '[["用户规则", "必须保留"]]\n',
            self.project / "speaker_map.json": '{"发言人1": "自定义主播"}\n',
            self.project / "outlines" / "sample_outline.md": "# 用户自己的大纲\n",
            self.project / "glossary" / "README.md": "# 用户自己的术语说明\n",
        }
        for path, content in existing.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        first = self.run_cli("init", "--project", self.project)
        second = self.run_cli("init", "--project", self.project)

        for path, content in existing.items():
            self.assertEqual(path.read_text(encoding="utf-8"), content)
        self.assertIn("保留已有文件", first.stdout)
        self.assertIn("保留已有文件", second.stdout)
        for directory in (
            "00_inbox",
            "01_raw_docx",
            "02_normalized_text",
            "03_review_draft",
            "04_final_text",
            "05_agent_chunks",
            "outlines",
            "glossary",
            "manifests",
        ):
            self.assertTrue((self.project / directory).is_dir(), directory)

    def test_prepare_parses_blank_lines_speakers_and_outline(self) -> None:
        self.init_project()
        self.prepare()

        review = self.load_json(self.episode_path("03_review_draft", "review.json"))
        questions = self.load_json(
            self.episode_path("03_review_draft", "questions.json")
        )
        manifest = self.load_json(self.project / "manifests" / "ep001.json")

        self.assertEqual(review["schema_version"], "podcast-proofreader.review.v1")
        self.assertEqual(review["parse"]["mode"], "speaker_timestamp")
        self.assertEqual(len(review["blocks"]), 5)
        self.assertEqual(
            [block["speaker"] for block in review["blocks"]],
            ["周原", "林青", "周原", "林青", "周原"],
        )
        self.assertEqual(
            review["blocks"][0]["text"],
            "欢迎收听《植物夜话》，今天我们聊室内植物。",
        )
        self.assertEqual(
            review["blocks"][1]["text"],
            "大家好，我是林青。最近回南天比较明显，养护时要注意通风。",
        )
        self.assertNotIn("\n\n", "\n".join(block["text"] for block in review["blocks"]))

        self.assertEqual(review["title"], "Vol.01 回南天里的室内植物养护")
        self.assertEqual(review["people"], ["周原", "林青"])
        self.assertIn("如何通过通风", review["description"])
        self.assertEqual(
            [(chapter["start"], chapter["title"]) for chapter in review["chapters"]],
            [
                ("00:00:00", "开场"),
                ("00:00:22", "龟背竹与环境"),
                ("00:00:38", "浇水建议"),
            ],
        )
        self.assertEqual(len(review["term_hints"]), 2)
        self.assertEqual(review["correction_stats"][0]["hits"], 1)
        self.assertEqual([item["id"] for item in questions["items"]], ["Q001"])
        self.assertEqual(questions["items"][0]["original"], "龟背猪")
        self.assertEqual(manifest["status"], "needs_agent_review")

    def test_agent_review_adds_semantic_question_and_updates_status(self) -> None:
        self.init_project()
        self.prepare()

        result = self.run_cli(
            "agent-review",
            "--project",
            self.project,
            "--ep-id",
            "ep001",
            "--input",
            DEMO / "agent_review.json",
        )

        questions = self.load_json(
            self.episode_path("03_review_draft", "questions.json")
        )
        manifest = self.load_json(self.project / "manifests" / "ep001.json")
        editor_review = self.episode_path(
            "03_review_draft", "editor-review.md"
        ).read_text(encoding="utf-8")

        self.assertTrue(questions["agent_review"]["completed"])
        self.assertEqual(
            questions["agent_review"]["notes"], "已按大纲完成全文语义复核。"
        )
        self.assertEqual([item["id"] for item in questions["items"]], ["Q001", "Q002"])
        self.assertEqual(questions["items"][1]["block_id"], "B00003")
        self.assertEqual(questions["items"][1]["category"], "外文术语")
        self.assertEqual(manifest["status"], "awaiting_editor")
        self.assertEqual(manifest["counts"]["questions_pending"], 2)
        self.assertIn("Q002 · 外文术语", editor_review)
        self.assertIn("2 条待确认", result.stdout)

    def test_agent_review_rejects_empty_or_misspelled_payload(self) -> None:
        self.init_project()
        self.prepare()
        questions_path = self.episode_path("03_review_draft", "questions.json")
        original_questions = questions_path.read_bytes()
        invalid_payloads = (
            ({}, "显式包含 edits 和 questions"),
            (
                {"edits": [], "questions": [], "questons": []},
                "包含未知字段",
            ),
        )

        for index, (payload, expected_message) in enumerate(
            invalid_payloads, start=1
        ):
            with self.subTest(payload=payload):
                payload_path = self.write_json(
                    self.workspace / f"invalid-agent-review-{index}.json", payload
                )
                result = self.run_cli(
                    "agent-review",
                    "--project",
                    self.project,
                    "--ep-id",
                    "ep001",
                    "--input",
                    payload_path,
                    expected_returncode=2,
                )
                self.assertIn(expected_message, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(questions_path.read_bytes(), original_questions)

        manifest = self.load_json(self.project / "manifests" / "ep001.json")
        self.assertEqual(manifest["status"], "needs_agent_review")

    def test_resolve_is_blocked_before_agent_review(self) -> None:
        self.init_project()
        self.prepare()

        result = self.run_cli(
            "resolve",
            "--project",
            self.project,
            "--ep-id",
            "ep001",
            "--answers",
            DEMO / "answers.json",
            expected_returncode=2,
        )

        self.assertIn("Agent 尚未完成语义复核", result.stderr)
        questions = self.load_json(
            self.episode_path("03_review_draft", "questions.json")
        )
        self.assertTrue(all(item["status"] == "pending" for item in questions["items"]))

    def test_finalize_is_blocked_while_any_question_is_pending(self) -> None:
        self.init_project()
        self.prepare()
        self.agent_review()
        partial_answers = self.write_json(
            self.workspace / "partial-answers.json",
            {"answers": {"Q001": {"action": "accept"}}},
        )
        self.run_cli(
            "resolve",
            "--project",
            self.project,
            "--ep-id",
            "ep001",
            "--answers",
            partial_answers,
        )

        result = self.run_cli(
            "finalize",
            "--project",
            self.project,
            "--ep-id",
            "ep001",
            expected_returncode=2,
        )

        self.assertIn("仍有 1 条待确认疑点", result.stderr)
        self.assertFalse(self.episode_path("04_final_text", "final.md").exists())
        manifest = self.load_json(self.project / "manifests" / "ep001.json")
        self.assertEqual(manifest["status"], "awaiting_editor")
        self.assertEqual(manifest["counts"]["questions_pending"], 1)

    def test_finalize_generates_final_timeline_and_chunks(self) -> None:
        self.init_project()
        self.prepare()
        self.agent_review()
        self.resolve_all()

        result = self.run_cli(
            "finalize",
            "--project",
            self.project,
            "--ep-id",
            "ep001",
            "--chunk-chars",
            "200",
        )

        final_path = self.episode_path("04_final_text", "final.md")
        timeline_path = self.episode_path("04_final_text", "timeline.json")
        chunks_path = self.episode_path("05_agent_chunks", "chunks.jsonl")
        final_text = final_path.read_text(encoding="utf-8")
        timeline = self.load_json(timeline_path)
        chunks = [
            json.loads(line)
            for line in chunks_path.read_text(encoding="utf-8").splitlines()
            if line
        ]
        manifest = self.load_json(self.project / "manifests" / "ep001.json")

        self.assertIn("# Vol.01 回南天里的室内植物养护", final_text)
        self.assertIn("最近回南天比较明显", final_text)
        self.assertIn("我们先从龟背竹讲起", final_text)
        self.assertNotIn("龟背猪", final_text)
        self.assertIn("Monstera deliciosa", final_text)
        self.assertIn("## 时间轴", final_text)
        self.assertIn("## 文字稿", final_text)
        self.assertEqual(
            timeline["schema_version"], "podcast-proofreader.timeline.v1"
        )
        self.assertEqual(len(timeline["chapters"]), 3)
        self.assertEqual(
            sum(chapter["block_count"] for chapter in timeline["chapters"]), 5
        )
        self.assertEqual(len(chunks), 3)
        self.assertTrue(
            all(
                chunk["schema_version"] == "podcast-proofreader.chunk.v1"
                for chunk in chunks
            )
        )
        self.assertTrue(all(chunk["episode_id"] == "ep001" for chunk in chunks))
        self.assertEqual(manifest["status"], "finalized")
        self.assertEqual(manifest["counts"]["questions_pending"], 0)
        self.assertIn("最终交付已生成", result.stdout)

    def test_long_single_block_is_split_into_bounded_structured_chunks(self) -> None:
        self.init_project()
        long_text = "长" * 650
        source = self.workspace / "long-block.txt"
        source.write_text(
            f"发言人1  00:00\n{long_text}\n",
            encoding="utf-8",
        )
        self.run_cli(
            "prepare",
            "--project",
            self.project,
            "--input",
            source,
            "--speaker-map",
            DEMO / "speaker_map.json",
            "--ep-id",
            "ep-long",
        )
        empty_review = self.write_json(
            self.workspace / "empty-agent-review.json",
            {"edits": [], "questions": [], "notes": "长段落切片测试"},
        )
        self.run_cli(
            "agent-review",
            "--project",
            self.project,
            "--ep-id",
            "ep-long",
            "--input",
            empty_review,
        )
        self.run_cli(
            "finalize",
            "--project",
            self.project,
            "--ep-id",
            "ep-long",
            "--chunk-chars",
            "200",
        )

        chunks_path = (
            self.project
            / "05_agent_chunks"
            / "ep-long"
            / "ep-long.chunks.jsonl"
        )
        chunks = [
            json.loads(line)
            for line in chunks_path.read_text(encoding="utf-8").splitlines()
            if line
        ]

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            with self.subTest(chunk_id=chunk["id"]):
                self.assertLessEqual(len(chunk["text"]), 200)
                self.assertLessEqual(chunk["char_count"], 200)
                self.assertEqual(chunk["block_ids"], ["B00001"])
                self.assertTrue(chunk["turns"])
                self.assertEqual(
                    chunk["char_count"],
                    sum(len(turn["text"]) for turn in chunk["turns"]),
                )
                self.assertTrue(
                    all(turn["block_id"] == "B00001" for turn in chunk["turns"])
                )
                self.assertTrue(
                    all(
                        {
                            "block_id",
                            "speaker",
                            "start",
                            "end",
                            "segment_index",
                            "segment_count",
                            "text",
                        }.issubset(turn)
                        for turn in chunk["turns"]
                    )
                )
        reconstructed = "".join(
            turn["text"] for chunk in chunks for turn in chunk["turns"]
        )
        self.assertEqual(reconstructed, long_text)

    def test_resolve_is_rejected_after_episode_is_finalized(self) -> None:
        self.init_project()
        self.prepare()
        self.agent_review()
        self.resolve_all()
        self.run_cli(
            "finalize",
            "--project",
            self.project,
            "--ep-id",
            "ep001",
        )
        final_path = self.episode_path("04_final_text", "final.md")
        questions_path = self.episode_path("03_review_draft", "questions.json")
        final_before = final_path.read_bytes()
        questions_before = questions_path.read_bytes()

        result = self.run_cli(
            "resolve",
            "--project",
            self.project,
            "--ep-id",
            "ep001",
            "--answers",
            DEMO / "answers.json",
            expected_returncode=2,
        )

        self.assertIn("已经 finalized", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(final_path.read_bytes(), final_before)
        self.assertEqual(questions_path.read_bytes(), questions_before)

    def test_minute_only_timestamp_allows_values_over_sixty(self) -> None:
        self.init_project()
        source = self.workspace / "long-timestamp.txt"
        source.write_text(
            "发言人1  00:00\n开场。\n\n"
            "发言人2  75:00\n第七十五分钟继续讨论。\n",
            encoding="utf-8",
        )

        self.run_cli(
            "prepare",
            "--project",
            self.project,
            "--input",
            source,
            "--speaker-map",
            DEMO / "speaker_map.json",
            "--ep-id",
            "ep075",
        )

        review = self.load_json(
            self.project
            / "03_review_draft"
            / "ep075"
            / "ep075.review.json"
        )
        self.assertEqual(
            [block["start_seconds"] for block in review["blocks"]],
            [0.0, 4500.0],
        )
        self.assertEqual(review["blocks"][1]["start"], "01:15:00")

    def test_reverse_unordered_and_too_short_duration_are_rejected(self) -> None:
        self.init_project()
        cases = (
            (
                "reverse.srt",
                "1\n00:00:10,000 --> 00:00:05,000\n发言人1：反向范围\n",
                "ep-reverse",
                (),
                "时间范围反向",
            ),
            (
                "unordered.srt",
                "1\n00:00:10,000 --> 00:00:11,000\n发言人1：较晚\n\n"
                "2\n00:00:05,000 --> 00:00:06,000\n发言人1：较早\n",
                "ep-unordered",
                (),
                "不是升序",
            ),
            (
                "duration.txt",
                (DEMO / "transcript.txt").read_text(encoding="utf-8"),
                "ep-short",
                ("--duration", "00:30"),
                "节目总时长",
            ),
        )

        for filename, content, episode_id, extra_args, expected_message in cases:
            with self.subTest(episode_id=episode_id):
                source = self.workspace / filename
                source.write_text(content, encoding="utf-8")
                result = self.run_cli(
                    "prepare",
                    "--project",
                    self.project,
                    "--input",
                    source,
                    "--speaker-map",
                    DEMO / "speaker_map.json",
                    "--ep-id",
                    episode_id,
                    *extra_args,
                    expected_returncode=2,
                )
                self.assertIn(expected_message, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(
                    (self.project / "manifests" / f"{episode_id}.json").exists()
                )

    def test_missing_input_and_missing_episode_status_are_clean_errors(self) -> None:
        self.init_project()
        missing_input = self.run_cli(
            "prepare",
            "--project",
            self.project,
            "--input",
            self.workspace / "not-found.txt",
            "--ep-id",
            "ep-missing-input",
            expected_returncode=2,
        )
        missing_status = self.run_cli(
            "status",
            "--project",
            self.project,
            "--ep-id",
            "ep-missing-status",
            expected_returncode=2,
        )

        self.assertIn("转写稿不存在", missing_input.stderr)
        self.assertIn("找不到期号", missing_status.stderr)
        for result in (missing_input, missing_status):
            self.assertNotIn("Traceback", result.stdout)
            self.assertNotIn("Traceback", result.stderr)

    def test_prepare_with_identical_inputs_is_idempotent(self) -> None:
        self.init_project()
        self.prepare()
        tracked_paths = [
            self.episode_path("02_normalized_text", "raw.txt"),
            self.episode_path("03_review_draft", "review.json"),
            self.episode_path("03_review_draft", "questions.json"),
            self.episode_path("03_review_draft", "editor-review.md"),
            self.project / "manifests" / "ep001.json",
        ]
        before = {path: path.read_bytes() for path in tracked_paths}

        result = self.prepare()

        after = {path: path.read_bytes() for path in tracked_paths}
        self.assertEqual(after, before)
        self.assertIn("相同输入准备完成，无需重复执行", result.stdout)

    def test_prepare_with_changed_input_requires_force(self) -> None:
        self.init_project()
        self.prepare()
        review_path = self.episode_path("03_review_draft", "review.json")
        original_review = review_path.read_bytes()
        original_archive = (
            self.project / "01_raw_docx" / "ep001" / self.transcript.name
        )
        original_archive_bytes = original_archive.read_bytes()
        self.transcript.write_text(
            self.transcript.read_text(encoding="utf-8")
            + "\n发言人2  01:02\n这是补充内容。\n",
            encoding="utf-8",
        )

        rejected = self.run_cli(
            "prepare",
            "--project",
            self.project,
            "--input",
            self.transcript,
            "--outline",
            DEMO / "outline.md",
            "--speaker-map",
            DEMO / "speaker_map.json",
            "--corrections",
            DEMO / "corrections.json",
            "--ep-id",
            "ep001",
            expected_returncode=2,
        )

        self.assertIn("输入不同", rejected.stderr)
        self.assertIn("--force", rejected.stderr)
        self.assertEqual(review_path.read_bytes(), original_review)

        self.prepare(force=True)
        rebuilt = self.load_json(review_path)
        self.assertEqual(len(rebuilt["blocks"]), 6)
        self.assertEqual(rebuilt["blocks"][-1]["text"], "这是补充内容。")
        archives = sorted((self.project / "01_raw_docx" / "ep001").glob("*.txt"))
        self.assertEqual(len(archives), 2)
        self.assertEqual(original_archive.read_bytes(), original_archive_bytes)
        self.assertIn(self.transcript.read_bytes(), [path.read_bytes() for path in archives])

    def test_force_rebuild_does_not_reuse_stale_final_delivery(self) -> None:
        self.init_project()
        self.prepare()
        self.agent_review()
        self.resolve_all()
        self.run_cli(
            "finalize",
            "--project",
            self.project,
            "--ep-id",
            "ep001",
        )
        final_path = self.episode_path("04_final_text", "final.md")
        old_final = final_path.read_bytes()
        self.transcript.write_text(
            self.transcript.read_text(encoding="utf-8")
            + "\n发言人2  01:02\n这是强制重建后的新内容。\n",
            encoding="utf-8",
        )

        self.prepare(force=True)
        rebuilt_manifest = self.load_json(self.project / "manifests" / "ep001.json")
        self.assertEqual(rebuilt_manifest["status"], "needs_agent_review")
        self.agent_review()
        self.resolve_all()
        result = self.run_cli(
            "finalize",
            "--project",
            self.project,
            "--ep-id",
            "ep001",
        )

        new_final = final_path.read_bytes()
        self.assertNotEqual(new_final, old_final)
        self.assertIn(
            "这是强制重建后的新内容",
            new_final.decode("utf-8"),
        )
        self.assertIn("最终交付已生成", result.stdout)
        self.assertNotIn("最终交付已存在", result.stdout)

    def test_docx_table_cell_preserves_multiple_paragraphs(self) -> None:
        self.init_project()
        docx_path = self.workspace / "table.docx"
        namespace = (
            "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        )
        document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{namespace}">
  <w:body>
    <w:tbl>
      <w:tr>
        <w:tc>
          <w:p><w:r><w:t>发言人1  00:00</w:t></w:r></w:p>
          <w:p><w:r><w:t>第一段内容</w:t></w:r></w:p>
          <w:p><w:r><w:t>第二段内容</w:t></w:r></w:p>
        </w:tc>
        <w:tc>
          <w:p><w:r><w:t>旁栏甲</w:t></w:r></w:p>
          <w:p><w:r><w:t>旁栏乙</w:t></w:r></w:p>
        </w:tc>
      </w:tr>
    </w:tbl>
  </w:body>
</w:document>
"""
        with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", document_xml)

        self.run_cli(
            "prepare",
            "--project",
            self.project,
            "--input",
            docx_path,
            "--speaker-map",
            DEMO / "speaker_map.json",
            "--ep-id",
            "ep-docx",
        )

        normalized = (
            self.project
            / "02_normalized_text"
            / "ep-docx"
            / "ep-docx.raw.txt"
        ).read_text(encoding="utf-8")
        review = self.load_json(
            self.project
            / "03_review_draft"
            / "ep-docx"
            / "ep-docx.review.json"
        )
        expected = "第一段内容\n第二段内容\t旁栏甲\n旁栏乙"
        self.assertIn(
            "发言人1  00:00\n第一段内容\n第二段内容\t旁栏甲\n旁栏乙",
            normalized,
        )
        self.assertEqual(len(review["blocks"]), 1)
        self.assertEqual(review["blocks"][0]["speaker"], "周原")
        self.assertEqual(review["blocks"][0]["text"], expected)

    def test_illegal_episode_ids_are_rejected_without_writing_outputs(self) -> None:
        self.init_project()

        for episode_id in ("../escape", "ep/001", ".", "含空格"):
            with self.subTest(episode_id=episode_id):
                result = self.run_cli(
                    "prepare",
                    "--project",
                    self.project,
                    "--input",
                    self.transcript,
                    "--ep-id",
                    episode_id,
                    expected_returncode=2,
                )
                self.assertIn("期号", result.stderr)

        self.assertEqual(list((self.project / "manifests").glob("*.json")), [])
        self.assertFalse((self.workspace / "escape").exists())


    # --- 按期号自动发现 outlines/ 和 config/by_ep/ 下的输入 ---

    def prepare_by_convention(
        self, *, expected_returncode: int = 0
    ) -> subprocess.CompletedProcess[str]:
        return self.run_cli(
            "prepare",
            "--project",
            self.project,
            "--input",
            self.transcript,
            "--ep-id",
            "ep001",
            expected_returncode=expected_returncode,
        )

    def test_outline_and_episode_config_are_discovered_by_episode_id(self) -> None:
        self.init_project()
        shutil.copy2(DEMO / "outline.md", self.project / "outlines" / "ep001.outline.md")
        by_ep = self.project / "config" / "by_ep"
        self.write_json(by_ep / "ep001.speaker_map.json", {"发言人1": "周原"})

        result = self.prepare_by_convention()

        self.assertIn("outlines/ep001.outline.md", result.stdout)
        self.assertIn("config/by_ep/ep001.speaker_map.json", result.stdout)
        manifest = self.load_json(self.project / "manifests" / "ep001.json")
        self.assertEqual(manifest["inputs"]["outline"], "outlines/ep001.outline.md")
        self.assertEqual(
            manifest["inputs"]["speaker_map"],
            "config/by_ep/ep001.speaker_map.json",
        )
        review = self.load_json(
            self.project / "03_review_draft" / "ep001" / "ep001.review.json"
        )
        self.assertEqual(review["blocks"][0]["speaker"], "周原")

    def test_explicit_flags_win_over_episode_convention(self) -> None:
        self.init_project()
        by_ep = self.project / "config" / "by_ep"
        self.write_json(by_ep / "ep001.speaker_map.json", {"发言人1": "不该被使用"})

        self.run_cli(
            "prepare",
            "--project",
            self.project,
            "--input",
            self.transcript,
            "--ep-id",
            "ep001",
            "--speaker-map",
            DEMO / "speaker_map.json",
        )

        review = self.load_json(
            self.project / "03_review_draft" / "ep001" / "ep001.review.json"
        )
        self.assertEqual(review["blocks"][0]["speaker"], "周原")

    def test_episode_corrections_override_global_instead_of_conflicting(self) -> None:
        self.init_project()
        self.write_json(
            self.project / "corrections.json",
            [{"from": "回蓝天", "to": "回南天"}, {"from": "室内植物", "to": "全局段"}],
        )
        self.write_json(
            self.project / "config" / "by_ep" / "ep001.corrections.json",
            [{"from": "室内植物", "to": "分期段"}],
        )

        self.prepare_by_convention()

        review = self.load_json(
            self.project / "03_review_draft" / "ep001" / "ep001.review.json"
        )
        text = "\n".join(block["text"] for block in review["blocks"])
        self.assertIn("分期段", text)
        self.assertNotIn("全局段", text)
        self.assertIn("回南天", text)

    def test_episode_chapters_used_when_outline_has_no_timeline(self) -> None:
        self.init_project()
        (self.project / "outlines" / "ep001.outline.md").write_text(
            "# 演示节目\n\n## 节目介绍\n一句话简介。\n", encoding="utf-8"
        )
        self.write_json(
            self.project / "config" / "by_ep" / "ep001.chapters.json",
            [["00:00", "开场"], ["00:08", "正题"]],
        )

        result = self.prepare_by_convention()

        self.assertIn("ep001.chapters.json", result.stdout)
        review = self.load_json(
            self.project / "03_review_draft" / "ep001" / "ep001.review.json"
        )
        self.assertEqual(
            [chapter["title"] for chapter in review["chapters"]], ["开场", "正题"]
        )

    def test_episode_chapters_apply_to_explicitly_passed_outline_too(self) -> None:
        self.init_project()
        outline = self.workspace / "custom.outline.md"
        outline.write_text("# 演示节目\n\n## 节目介绍\n简介。\n", encoding="utf-8")
        self.write_json(
            self.project / "config" / "by_ep" / "ep001.chapters.json",
            [["00:00", "开场"], ["00:08", "正题"]],
        )

        self.run_cli(
            "prepare",
            "--project",
            self.project,
            "--input",
            self.transcript,
            "--ep-id",
            "ep001",
            "--outline",
            outline,
        )

        review = self.load_json(
            self.project / "03_review_draft" / "ep001" / "ep001.review.json"
        )
        self.assertEqual(
            [chapter["title"] for chapter in review["chapters"]], ["开场", "正题"]
        )

    def test_outline_timeline_wins_over_episode_chapters(self) -> None:
        self.init_project()
        shutil.copy2(DEMO / "outline.md", self.project / "outlines" / "ep001.outline.md")
        self.write_json(
            self.project / "config" / "by_ep" / "ep001.chapters.json",
            [["00:00", "不该被使用"]],
        )

        self.prepare_by_convention()

        review = self.load_json(
            self.project / "03_review_draft" / "ep001" / "ep001.review.json"
        )
        titles = [chapter["title"] for chapter in review["chapters"]]
        self.assertNotIn("不该被使用", titles)


    # --- 大纲预检 ---

    def write_outline(self, body: str) -> Path:
        path = self.workspace / "outline.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_duplicate_timeline_sections_are_rejected_with_line_numbers(self) -> None:
        outline = self.write_outline(
            "# 演示节目\n\n"
            "## 时间轴\n"
            "- 00:00 开场\n\n"
            "## 完整章节点（备用）\n"
            "- 00:00 开场\n"
        )
        result = self.run_cli("check-outline", outline, expected_returncode=2)
        self.assertIn("时间轴", result.stdout + result.stderr)
        self.assertIn("第 3 行", result.stdout + result.stderr)
        self.assertIn("第 6 行", result.stdout + result.stderr)

    def test_non_chapter_line_inside_timeline_reports_line_number(self) -> None:
        outline = self.write_outline(
            "# 演示节目\n\n## 时间轴\n- 00:00 开场\n- 这行不是章节\n"
        )
        result = self.run_cli("check-outline", outline, expected_returncode=2)
        self.assertIn("第 5 行", result.stdout + result.stderr)

    def test_clean_outline_passes_and_lists_degradations(self) -> None:
        outline = self.write_outline("# 演示节目\n\n## 时间轴\n- 00:00 开场\n")
        result = self.run_cli("check-outline", outline)
        self.assertIn("[通过]", result.stdout)
        self.assertIn("术语线索", result.stdout)
        self.assertIn("0 份会导致 prepare 失败", result.stdout)


    # --- manifests/ 混入外来文件 ---

    def test_status_skips_foreign_manifests_instead_of_crashing(self) -> None:
        self.init_project()
        # 旧流水线留下的同名文件：status 里 status 是 dict 而不是字符串。
        self.write_json(
            self.project / "manifests" / "ep900.json",
            {"episode_id": "ep900", "status": {"ai_review_draft": True}},
        )

        result = self.run_cli("status", "--project", self.project)

        self.assertIn("ep900.json", result.stdout)
        self.assertIn("跳过", result.stdout)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
