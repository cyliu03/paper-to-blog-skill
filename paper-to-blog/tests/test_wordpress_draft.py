from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from paper_assets import atomic_json, compute_content_hash, sha256_file
from wordpress_draft import NotConfiguredError, run


class MockWordPressHandler(BaseHTTPRequestHandler):
    media_calls = 0
    post_calls: list[str] = []
    term_counter = 10

    def log_message(self, format: str, *args: object) -> None:
        return

    def send_json(self, status: int, data: object) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path.startswith("/site-info"):
            self.send_json(200, {"quota_space": {"bytes_allowed": 1024 * 1024 * 1024, "bytes_used": 1024}})
        elif "/categories" in self.path or "/tags" in self.path:
            self.send_json(200, [])
        else:
            self.send_json(404, {"message": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        if self.path.endswith("/media"):
            type(self).media_calls += 1
            self.send_json(201, {"id": 7, "source_url": "https://cdn.example.test/figure-1.png"})
        elif self.path.endswith("/categories") or self.path.endswith("/tags"):
            type(self).term_counter += 1
            self.send_json(201, {"id": type(self).term_counter})
        elif "/posts" in self.path:
            type(self).post_calls.append(self.path)
            self.send_json(201, {"id": 42, "link": "https://example.wordpress.com/?p=42", "status": "draft"})
        else:
            self.send_json(404, {"message": "not found"})


def create_approved_bundle(root: Path) -> Path:
    bundle = root / "bundle"
    (bundle / "source").mkdir(parents=True)
    (bundle / "figures" / "selected").mkdir(parents=True)
    pdf = bundle / "source" / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% deterministic test fixture\n")
    figure = bundle / "figures" / "selected" / "figure-1.png"
    figure.write_bytes(b"\x89PNG\r\n\x1a\nsource-paper-figure")
    article_md = "# 测试论文精读\n\n这是用于测试WordPress草稿适配器的正文。\n\n![Figure 1](figures/selected/figure-1.png)\n"
    article_html = '<h1>测试论文精读</h1><p>这是用于测试WordPress草稿适配器的正文。</p><img src="figures/selected/figure-1.png" alt="Figure 1">'
    (bundle / "article.md").write_text(article_md, encoding="utf-8")
    (bundle / "article.html").write_text(article_html, encoding="utf-8")
    (bundle / "preview.md").write_text("# 预览检查\n\n图片来源和文章内容均已核对，可以进入草稿上传测试。\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "paper": {"local_pdf": "source/paper.pdf", "sha256": sha256_file(pdf)},
        "figure_candidates": [],
        "figures": [
            {
                "figure_id": "Figure 1",
                "file": "figures/selected/figure-1.png",
                "page": 1,
                "caption": "A source-paper figure.",
                "source_type": "main",
                "method": "embedded",
                "crop_box_pdf_points": None,
                "sha256": sha256_file(figure),
            }
        ],
        "blog": {
            "title": "测试论文精读",
            "summary": "测试摘要",
            "categories": ["人工智能"],
            "tags": ["论文精读", "测试"],
            "language": "zh-CN",
            "article_markdown": "article.md",
            "article_html": "article.html",
            "preview": "preview.md",
            "approved_content_hash": None,
        },
        "status": "preview_ready",
    }
    content_hash = compute_content_hash(bundle, manifest)
    manifest["blog"]["approved_content_hash"] = content_hash
    atomic_json(bundle / "manifest.json", manifest)
    atomic_json(
        bundle / "publication.json",
        {
            "schema_version": 1,
            "approved_content_hash": content_hash,
            "wordpress": {"status": "pending", "site": None, "post_id": None, "edit_url": None, "media": {}, "last_error": None},
            "csdn": {"status": "pending", "draft_url": None, "last_updated": None, "last_error": None},
        },
    )
    return bundle


class WordPressDraftTests(unittest.TestCase):
    def setUp(self) -> None:
        MockWordPressHandler.media_calls = 0
        MockWordPressHandler.post_calls = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), MockWordPressHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def args(self, bundle: Path) -> argparse.Namespace:
        port = self.server.server_address[1]
        return argparse.Namespace(
            bundle=bundle,
            api_base=f"http://127.0.0.1:{port}/wp/v2/sites/{{site}}",
            site_info_url=f"http://127.0.0.1:{port}/site-info",
            timeout=5,
            dry_run=False,
        )

    def test_create_then_update_is_idempotent_for_media(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"PAPER_BLOG_WP_SITE": "example.wordpress.com", "PAPER_BLOG_WP_TOKEN": "test-token"}, clear=False
        ):
            bundle = create_approved_bundle(Path(temp))
            first = run(self.args(bundle))
            second = run(self.args(bundle))
            self.assertEqual(first["status"], "draft")
            self.assertEqual(second["post_id"], 42)
            self.assertEqual(MockWordPressHandler.media_calls, 1)
            self.assertTrue(MockWordPressHandler.post_calls[0].endswith("/posts"))
            self.assertTrue(MockWordPressHandler.post_calls[1].endswith("/posts/42"))
            publication = json.loads((bundle / "publication.json").read_text(encoding="utf-8"))
            self.assertEqual(publication["wordpress"]["status"], "draft")
            self.assertNotIn("test-token", (bundle / "publication.json").read_text(encoding="utf-8"))

    def test_missing_configuration_marks_not_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            bundle = create_approved_bundle(Path(temp))
            with self.assertRaises(NotConfiguredError):
                run(self.args(bundle))
            publication = json.loads((bundle / "publication.json").read_text(encoding="utf-8"))
            self.assertEqual(publication["wordpress"]["status"], "not_configured")


if __name__ == "__main__":
    unittest.main()
