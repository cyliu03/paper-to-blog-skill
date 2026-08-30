from __future__ import annotations

import re
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent


class SkillStructureTests(unittest.TestCase):
    def test_frontmatter_and_agent_metadata(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill_text.startswith("---\n"))
        frontmatter = skill_text.split("---\n", 2)[1]

        name_match = re.search(r"^name:\s*([^\n]+)$", frontmatter, re.MULTILINE)
        description_match = re.search(r"^description:\s*([^\n]+)$", frontmatter, re.MULTILINE)
        self.assertIsNotNone(name_match)
        self.assertIsNotNone(description_match)
        self.assertEqual(name_match.group(1).strip(), SKILL_ROOT.name)
        self.assertLessEqual(len(description_match.group(1).strip()), 1024)

        agent_text = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("$paper-to-blog", agent_text)

    def test_relative_markdown_links_exist(self) -> None:
        for markdown_file in SKILL_ROOT.rglob("*.md"):
            text = markdown_file.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
                if "://" in target or target.startswith("#"):
                    continue
                path = (markdown_file.parent / target.split("#", 1)[0]).resolve()
                self.assertTrue(path.exists(), f"Broken link in {markdown_file}: {target}")

    def test_skill_contains_no_machine_specific_article_root(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("E:/paper_reader", skill_text)
        self.assertNotIn("C:/Users/", skill_text)


if __name__ == "__main__":
    unittest.main()
