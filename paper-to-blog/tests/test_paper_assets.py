from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageDraw


SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from paper_assets import BundleError, add_supplement, crop_figure, normalize_paper_source, prepare_bundle, register_figure, validate_bundle, validate_public_url


def make_pdf(path: Path, image_path: Path) -> None:
    image = Image.new("RGB", (500, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 460, 260), outline="black", width=5)
    draw.line((50, 240, 450, 70), fill="blue", width=8)
    image.save(image_path, format="PNG")
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 72), "A Test Paper", fontsize=18)
    page.insert_text((72, 110), "Figure 1. A deterministic source-paper figure.", fontsize=11)
    page.insert_image(fitz.Rect(72, 140, 540, 430), filename=str(image_path))
    page.draw_rect(fitz.Rect(72, 470, 540, 680), color=(0, 0, 0), width=2)
    page.insert_text((90, 510), "Vector Figure 2", fontsize=16)
    document.set_metadata({"title": "A Test Paper", "author": "Test Author"})
    document.save(path)
    document.close()


class PaperAssetsTests(unittest.TestCase):
    def test_prepare_register_crop_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "paper.pdf"
            source_image = root / "source.png"
            make_pdf(pdf, source_image)
            bundle = root / "bundle"
            prepare_bundle(str(pdf), bundle, 100)
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["paper"]["page_count"], 1)
            self.assertGreaterEqual(len(manifest["figure_candidates"]), 1)
            add_supplement(str(pdf), bundle, 72)
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["supplements"][0]["page_count"], 1)

            candidate = bundle / manifest["figure_candidates"][0]["file"]
            register_figure(
                argparse.Namespace(
                    bundle=bundle,
                    file=candidate,
                    page=1,
                    figure_id="Figure 1",
                    caption="A deterministic source-paper figure.",
                    source_type="main",
                    output_name=None,
                    replace=False,
                )
            )
            crop_figure(
                argparse.Namespace(
                    bundle=bundle,
                    page=1,
                    bbox=[72.0, 470.0, 540.0, 680.0],
                    figure_id="Figure 2",
                    caption="A vector figure faithfully cropped from the page.",
                    source_type="main",
                    output_name=None,
                    dpi=120,
                    replace=False,
                )
            )
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            figure_paths = [item["file"] for item in manifest["figures"]]
            manifest["blog"].update(
                {
                    "title": "测试论文精读",
                    "summary": "这是一篇用于验证流程的论文精读。",
                    "categories": ["人工智能"],
                    "tags": ["论文精读", "测试"],
                }
            )
            (bundle / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (bundle / "article.md").write_text(
                "# 测试论文精读\n\n这里是足够长的测试正文，用来验证论文原图引用和可追溯性。\n\n"
                + "\n\n".join(f"![论文原图]({path})\n\n来源：原论文。" for path in figure_paths),
                encoding="utf-8",
            )
            (bundle / "article.html").write_text(
                "<h1>测试论文精读</h1><p>这里是足够长的测试正文，用来验证论文原图引用和可追溯性。</p>"
                + "".join(f'<figure><img src="{path}" alt="论文原图"><figcaption>来源：原论文。</figcaption></figure>' for path in figure_paths),
                encoding="utf-8",
            )
            (bundle / "preview.md").write_text("# 预览检查\n\n- 图片来源已逐项核对。\n- 数据与作者解释已经分开陈述。\n", encoding="utf-8")
            result = validate_bundle(bundle, write_approval=True)
            self.assertTrue(result["ok"], result)
            self.assertRegex(result["content_hash"] or "", r"^[0-9a-f]{64}$")

    def test_validation_rejects_unregistered_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "paper.pdf"
            source_image = root / "source.png"
            make_pdf(pdf, source_image)
            bundle = root / "bundle"
            prepare_bundle(str(pdf), bundle, 72)
            rogue = bundle / "figures" / "selected" / "rogue.png"
            rogue.write_bytes(source_image.read_bytes())
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            manifest["blog"]["title"] = "测试"
            (bundle / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            (bundle / "article.md").write_text("# 测试\n\n足够长的正文。\n\n![未注册图片](figures/selected/rogue.png)\n", encoding="utf-8")
            (bundle / "article.html").write_text('<h1>测试</h1><p>足够长的正文。</p><img src="figures/selected/rogue.png">', encoding="utf-8")
            (bundle / "preview.md").write_text("# 检查\n\n这是一段长度足够的检查记录，用于测试。\n", encoding="utf-8")
            result = validate_bundle(bundle, write_approval=False)
            self.assertFalse(result["ok"])
            self.assertTrue(any("not registered" in item for item in result["errors"]))

    def test_private_network_source_is_rejected(self) -> None:
        with self.assertRaises(BundleError):
            validate_public_url("http://127.0.0.1/paper.pdf")

    def test_bare_doi_is_normalized(self) -> None:
        self.assertEqual(normalize_paper_source("doi:10.1234/example"), "https://doi.org/10.1234/example")


if __name__ == "__main__":
    unittest.main()
