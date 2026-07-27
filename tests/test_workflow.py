import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from docx import Document


SKILL_DIR = Path(__file__).resolve().parents[1]


class PodcastProofreaderWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.workspace = Path(self.temp_dir.name) / "PodcastTranscripts"

    def run_command(self, *args, cwd=None):
        return subprocess.run(
            [str(arg) for arg in args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )

    def initialize_workspace(self):
        self.run_command("bash", SKILL_DIR / "init_project.sh", self.workspace)

    def test_scaffold_contains_only_supported_workflow_directories(self):
        self.initialize_workspace()

        expected = {
            "00_inbox",
            "01_raw_docx",
            "02_normalized_text",
            "03_review_draft",
            "04_final_text",
            "outlines",
            "glossary",
            "manifests",
        }
        actual = {path.name for path in self.workspace.iterdir() if path.is_dir()}

        self.assertEqual(actual, expected)
        self.assertTrue((self.workspace / "corrections.json").is_file())
        self.assertTrue((self.workspace / "chapters.json").is_file())
        self.assertFalse((self.workspace / "05_agent_chunks").exists())
        self.assertFalse((self.workspace / "imports").exists())

        corrections = self.workspace / "corrections.json"
        corrections.write_text('[["custom", "kept"]]\n', encoding="utf-8")
        self.initialize_workspace()
        self.assertEqual(corrections.read_text(encoding="utf-8"), '[["custom", "kept"]]\n')

    def test_docx_import_and_structured_draft(self):
        self.initialize_workspace()

        source = self.workspace / "00_inbox" / "episode001.docx"
        document = Document()
        for line in (
            "发言人1   00:00",
            "欢迎来到 Open AI 的播客。",
            "",
            "发言人2   00:08",
            "谢谢邀请。",
        ):
            document.add_paragraph(line)
        document.save(source)

        self.run_command(
            sys.executable,
            SKILL_DIR / "scripts" / "import_docx.py",
            "--input",
            source,
            "--ep-id",
            "ep001",
            "--output-dir",
            "02_normalized_text",
            "--raw-dir",
            "01_raw_docx",
            "--manifest-dir",
            "manifests",
            "--title",
            "测试节目",
            cwd=self.workspace,
        )

        (self.workspace / "corrections.json").write_text(
            json.dumps([["Open AI", "OpenAI"]], ensure_ascii=False),
            encoding="utf-8",
        )
        (self.workspace / "chapters.json").write_text(
            json.dumps([["00:00", "开场"]], ensure_ascii=False),
            encoding="utf-8",
        )

        output = self.workspace / "03_review_draft" / "ep001" / "ep001.review.md"
        result = self.run_command(
            sys.executable,
            SKILL_DIR / "scripts" / "build_review.py",
            "--raw",
            "02_normalized_text/ep001/ep001.raw.txt",
            "--outline",
            "outlines/sample_outline.md",
            "--output",
            output,
            "--ep-id",
            "ep001",
            "--speaker-map",
            '{"发言人1":"嘉宾","发言人2":"主播"}',
            "--corrections",
            "corrections.json",
            "--chapters",
            "chapters.json",
            "--title",
            "测试节目",
            cwd=self.workspace,
        )

        draft = output.read_text(encoding="utf-8")
        self.assertIn("Parsed 2 speech blocks", result.stdout)
        self.assertIn("### [00:00] 开场", draft)
        self.assertIn("**嘉宾** [00:00]：欢迎来到 OpenAI 的播客。", draft)
        self.assertIn("**主播** [00:08]：谢谢邀请。", draft)
        self.assertIn("## 本期发言人", draft)

        manifest = json.loads(
            (self.workspace / "manifests" / "ep001.json").read_text(encoding="utf-8")
        )
        self.assertTrue(manifest["status"]["text_extracted"])
        self.assertNotIn("agent_chunks_exported", manifest["status"])
        self.assertNotIn("knowledge_base", manifest)

    def test_build_review_rejects_unparseable_transcript(self):
        self.initialize_workspace()
        raw = self.workspace / "02_normalized_text" / "ep001" / "ep001.raw.txt"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text("A transcript without speaker labels or timestamps.", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(SKILL_DIR / "scripts" / "build_review.py"),
                "--raw",
                str(raw),
                "--output",
                str(self.workspace / "review.md"),
                "--ep-id",
                "ep001",
            ],
            cwd=self.workspace,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("no speech blocks were parsed", result.stderr)

    def test_import_rejects_non_docx_input(self):
        self.initialize_workspace()
        source = self.workspace / "00_inbox" / "episode.txt"
        source.write_text("not a docx", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(SKILL_DIR / "scripts" / "import_docx.py"),
                "--input",
                str(source),
                "--ep-id",
                "ep001",
            ],
            cwd=self.workspace,
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Input must be a .docx file", result.stderr)


if __name__ == "__main__":
    unittest.main()
