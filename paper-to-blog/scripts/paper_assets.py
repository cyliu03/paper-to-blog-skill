#!/usr/bin/env python3
"""Prepare and validate traceable paper-to-blog article bundles."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html.parser
import ipaddress
import json
import mimetypes
import os
import re
import shutil
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import pymupdf as fitz
import requests


SCHEMA_VERSION = 1
MAX_PDF_BYTES = 100 * 1024 * 1024
MAX_HTML_BYTES = 5 * 1024 * 1024
USER_AGENT = "paper-to-blog/1.0 (personal research reading workflow)"


class BundleError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def is_url(value: str) -> bool:
    return urlparse(value).scheme.lower() in {"http", "https"}


def normalize_paper_source(value: str) -> str:
    stripped = value.strip()
    doi = re.sub(r"^doi:\s*", "", stripped, flags=re.IGNORECASE)
    if re.match(r"^10\.\d{4,9}/\S+$", doi):
        return "https://doi.org/" + quote_url_path(doi)
    return stripped


def quote_url_path(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="/()[]:;.,_-+")


def validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise BundleError(f"Only public HTTP(S) URLs are supported: {url}")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise BundleError(f"Cannot resolve source host: {parsed.hostname}") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise BundleError(f"Refusing a non-public source address: {parsed.hostname}")


def request_with_safe_redirects(session: requests.Session, url: str, *, stream: bool = False) -> requests.Response:
    current = url
    for _ in range(9):
        validate_public_url(current)
        response = session.get(
            current,
            headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.5"},
            timeout=(15, 60),
            allow_redirects=False,
            stream=stream,
        )
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise BundleError("Source returned a redirect without a destination")
            current = urljoin(current, location)
            continue
        response.raise_for_status()
        response.safe_final_url = current  # type: ignore[attr-defined]
        return response
    raise BundleError("Too many redirects while resolving the paper")


class PdfLinkParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value for key, value in attrs if value is not None}
        if tag.lower() == "meta":
            name = (values.get("name") or values.get("property") or "").lower()
            if name in {"citation_pdf_url", "wkhealth_pdf_url", "pdf_url"} and values.get("content"):
                self.links.append(values["content"])
        if tag.lower() == "a" and values.get("href"):
            href = values["href"]
            lowered = href.lower()
            if lowered.endswith(".pdf") or "/pdf" in lowered or "download" in lowered:
                self.links.append(href)


def known_pdf_candidates(url: str) -> list[str]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    candidates: list[str] = []
    if host.endswith("arxiv.org") and "/abs/" in parsed.path:
        identifier = parsed.path.split("/abs/", 1)[1]
        candidates.append(f"https://arxiv.org/pdf/{identifier}.pdf")
    if host.endswith("openreview.net"):
        query = parse_qs(parsed.query)
        if query.get("id"):
            candidates.append(f"https://openreview.net/pdf?id={query['id'][0]}")
    return candidates


def write_response_pdf(response: requests.Response, output: Path) -> None:
    total = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as stream:
        for chunk in response.iter_content(1024 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_PDF_BYTES:
                raise BundleError("PDF exceeds the 100 MB safety limit")
            stream.write(chunk)
    with output.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise BundleError("Resolved file is not a PDF")


def acquire_pdf(source: str, output: Path) -> tuple[str | None, str]:
    provided_source = source
    source = normalize_paper_source(source)
    local = Path(source).expanduser()
    if local.is_file():
        if local.suffix.lower() != ".pdf":
            with local.open("rb") as stream:
                if stream.read(5) != b"%PDF-":
                    raise BundleError("Local source is not a PDF")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, output)
        return None, str(local.resolve())
    if not is_url(source):
        raise BundleError(f"Paper source does not exist: {provided_source}")

    session = requests.Session()
    first = request_with_safe_redirects(session, source, stream=True)
    final_url = getattr(first, "safe_final_url", source)
    content_type = first.headers.get("Content-Type", "").lower()
    prefix = next(first.iter_content(8192), b"")
    if "pdf" in content_type or prefix.startswith(b"%PDF-"):
        # Re-fetch so the streaming iterator starts at byte zero.
        first.close()
        pdf_response = request_with_safe_redirects(session, final_url, stream=True)
        try:
            write_response_pdf(pdf_response, output)
        finally:
            pdf_response.close()
        return final_url, provided_source

    body = bytearray(prefix)
    for chunk in first.iter_content(65536):
        body.extend(chunk)
        if len(body) > MAX_HTML_BYTES:
            first.close()
            raise BundleError("Landing page is too large to inspect safely")
    first.close()
    parser = PdfLinkParser()
    parser.feed(bytes(body).decode(first.encoding or "utf-8", errors="replace"))
    candidates = known_pdf_candidates(final_url)
    candidates.extend(urljoin(final_url, href) for href in parser.links)
    seen: set[str] = set()
    errors: list[str] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            response = request_with_safe_redirects(session, candidate, stream=True)
            try:
                write_response_pdf(response, output)
                return getattr(response, "safe_final_url", candidate), provided_source
            finally:
                response.close()
        except (BundleError, requests.RequestException) as exc:
            errors.append(str(exc))
            if output.exists():
                output.unlink()
    detail = f" Attempts: {'; '.join(errors[:3])}" if errors else ""
    raise BundleError("No legally accessible PDF was found. Attach the PDF or provide a direct PDF link." + detail)


def relative_posix(path: Path, bundle: Path) -> str:
    return path.resolve().relative_to(bundle.resolve()).as_posix()


def prepare_bundle(source: str, bundle: Path, dpi: int) -> None:
    manifest_path = bundle / "manifest.json"
    if manifest_path.exists():
        raise BundleError(f"Bundle already exists; refusing to overwrite it: {bundle}")
    source_dir = bundle / "source"
    pages_dir = source_dir / "pages"
    extracted_dir = bundle / "figures" / "extracted"
    selected_dir = bundle / "figures" / "selected"
    for directory in (source_dir, pages_dir, extracted_dir, selected_dir):
        directory.mkdir(parents=True, exist_ok=True)

    pdf_path = source_dir / "paper.pdf"
    resolved_url, original_input = acquire_pdf(source, pdf_path)
    try:
        document = fitz.open(pdf_path)
    except Exception as exc:
        raise BundleError("The acquired PDF cannot be opened") from exc
    if document.needs_pass:
        document.close()
        raise BundleError("Password-protected PDFs are not supported")

    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    all_text: list[str] = []
    candidates: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for page_index, page in enumerate(document):
        page_number = page_index + 1
        all_text.append(f"\n\n===== PDF PAGE {page_number} =====\n\n{page.get_text('text')}")
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        pixmap.save(pages_dir / f"page-{page_number:04d}.png")
        for image_index, image_info in enumerate(page.get_images(full=True), start=1):
            xref = int(image_info[0])
            try:
                extracted = document.extract_image(xref)
            except Exception:
                continue
            width = int(extracted.get("width") or 0)
            height = int(extracted.get("height") or 0)
            if width < 100 or height < 100 or width * height < 40000:
                continue
            data = extracted.get("image")
            if not data:
                continue
            digest = hashlib.sha256(data).hexdigest()
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            ext = re.sub(r"[^a-z0-9]", "", str(extracted.get("ext") or "png").lower()) or "png"
            candidate_id = f"p{page_number:04d}-img{image_index:02d}-xref{xref}"
            image_path = extracted_dir / f"{candidate_id}.{ext}"
            image_path.write_bytes(data)
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "file": relative_posix(image_path, bundle),
                    "page": page_number,
                    "source_type": "main",
                    "source_pdf": "source/paper.pdf",
                    "xref": xref,
                    "width": width,
                    "height": height,
                    "sha256": digest,
                }
            )
    metadata = {str(k): str(v) for k, v in (document.metadata or {}).items() if v not in (None, "")}
    page_count = document.page_count
    document.close()

    (source_dir / "text.txt").write_text("".join(all_text), encoding="utf-8")
    source_record = {
        "input": original_input,
        "resolved_pdf_url": resolved_url,
        "acquired_at": utc_now(),
        "sha256": sha256_file(pdf_path),
    }
    atomic_json(source_dir / "source.json", source_record)

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "paper": {
            "input": original_input,
            "canonical_url": resolved_url or "",
            "doi": "",
            "title": metadata.get("title", ""),
            "authors": [],
            "venue": "",
            "year": "",
            "local_pdf": "source/paper.pdf",
            "sha256": source_record["sha256"],
            "page_count": page_count,
            "pdf_metadata": metadata,
        },
        "figure_candidates": candidates,
        "supplements": [],
        "figures": [],
        "blog": {
            "title": "",
            "summary": "",
            "categories": ["人工智能"],
            "tags": [],
            "language": "zh-CN",
            "article_markdown": "article.md",
            "article_html": "article.html",
            "preview": "preview.md",
            "approved_content_hash": None,
        },
        "status": "prepared",
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    atomic_json(manifest_path, manifest)
    publication = {
        "schema_version": SCHEMA_VERSION,
        "approved_content_hash": None,
        "wordpress": {"status": "not_configured", "site": None, "post_id": None, "edit_url": None, "media": {}, "last_error": None},
        "csdn": {"status": "pending", "draft_url": None, "last_updated": None, "last_error": None},
        "updated_at": utc_now(),
    }
    atomic_json(bundle / "publication.json", publication)

    template = Path(__file__).resolve().parent.parent / "assets" / "article-template.md"
    shutil.copy2(template, bundle / "article.md")
    (bundle / "article.html").write_text("<!-- Generate from the approved Markdown article. -->\n", encoding="utf-8")
    (bundle / "preview.md").write_text("# 预览检查\n\n生成文章后填写本文件，并在上传草稿前完成校验。\n", encoding="utf-8")
    print(json.dumps({"bundle": str(bundle.resolve()), "pages": page_count, "figure_candidates": len(candidates)}, ensure_ascii=False))


def add_supplement(source: str, bundle: Path, dpi: int) -> None:
    bundle = bundle.resolve()
    manifest = load_manifest(bundle)
    supplements = manifest.setdefault("supplements", [])
    index = len(supplements) + 1
    source_id = f"supplement-{index:02d}"
    relative_pdf = f"source/{source_id}.pdf"
    pdf_path = bundle / relative_pdf
    if pdf_path.exists():
        raise BundleError(f"Supplement destination already exists: {relative_pdf}")
    resolved_url, original_input = acquire_pdf(source, pdf_path)
    document = fitz.open(pdf_path)
    if document.needs_pass:
        document.close()
        raise BundleError("Password-protected supplementary PDFs are not supported")
    pages_dir = bundle / "source" / "supplement-pages" / source_id
    extracted_dir = bundle / "figures" / "extracted"
    pages_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir.mkdir(parents=True, exist_ok=True)
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    all_text: list[str] = []
    candidates: list[dict[str, Any]] = []
    seen_hashes = {item.get("sha256") for item in manifest.get("figure_candidates", [])}
    for page_index, page in enumerate(document):
        page_number = page_index + 1
        all_text.append(f"\n\n===== SUPPLEMENT PAGE {page_number} =====\n\n{page.get_text('text')}")
        page.get_pixmap(matrix=matrix, alpha=False).save(pages_dir / f"page-{page_number:04d}.png")
        for image_index, image_info in enumerate(page.get_images(full=True), start=1):
            xref = int(image_info[0])
            try:
                extracted = document.extract_image(xref)
            except Exception:
                continue
            width = int(extracted.get("width") or 0)
            height = int(extracted.get("height") or 0)
            data = extracted.get("image")
            if not data or width < 100 or height < 100 or width * height < 40000:
                continue
            digest = hashlib.sha256(data).hexdigest()
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            ext = re.sub(r"[^a-z0-9]", "", str(extracted.get("ext") or "png").lower()) or "png"
            candidate_id = f"{source_id}-p{page_number:04d}-img{image_index:02d}-xref{xref}"
            image_path = extracted_dir / f"{candidate_id}.{ext}"
            image_path.write_bytes(data)
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "file": relative_posix(image_path, bundle),
                    "page": page_number,
                    "source_type": "supplement",
                    "source_pdf": relative_pdf,
                    "xref": xref,
                    "width": width,
                    "height": height,
                    "sha256": digest,
                }
            )
    metadata = {str(k): str(v) for k, v in (document.metadata or {}).items() if v not in (None, "")}
    page_count = document.page_count
    document.close()
    (bundle / "source" / f"{source_id}.txt").write_text("".join(all_text), encoding="utf-8")
    supplement = {
        "source_id": source_id,
        "input": original_input,
        "canonical_url": resolved_url or "",
        "local_pdf": relative_pdf,
        "sha256": sha256_file(pdf_path),
        "page_count": page_count,
        "pdf_metadata": metadata,
        "acquired_at": utc_now(),
    }
    supplements.append(supplement)
    manifest.setdefault("figure_candidates", []).extend(candidates)
    manifest["blog"]["approved_content_hash"] = None
    manifest["status"] = "prepared"
    manifest["updated_at"] = utc_now()
    atomic_json(bundle / "manifest.json", manifest)
    print(json.dumps({"source_id": source_id, "pages": page_count, "figure_candidates": len(candidates)}, ensure_ascii=False))


def load_manifest(bundle: Path) -> dict[str, Any]:
    path = bundle / "manifest.json"
    if not path.is_file():
        raise BundleError(f"Missing manifest: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise BundleError("Unsupported manifest schema version")
    return data


def safe_selected_name(figure_id: str, suffix: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", figure_id.strip()).strip("-.").lower()
    return (stem or "figure") + suffix.lower()


def add_figure_record(manifest: dict[str, Any], record: dict[str, Any], replace: bool) -> None:
    figures = manifest.setdefault("figures", [])
    matches = [idx for idx, item in enumerate(figures) if item.get("figure_id") == record["figure_id"]]
    if matches and not replace:
        raise BundleError(f"Figure is already registered: {record['figure_id']}")
    if matches:
        figures[matches[0]] = record
    else:
        figures.append(record)


def crop_figure(args: argparse.Namespace) -> None:
    bundle = args.bundle.resolve()
    manifest = load_manifest(bundle)
    requested_source_pdf = getattr(args, "source_pdf", None)
    if args.source_type == "supplement" and not requested_source_pdf:
        raise BundleError("Supplement crops require --source-pdf")
    source_pdf = requested_source_pdf or manifest["paper"]["local_pdf"]
    pdf_path = (bundle / source_pdf).resolve()
    try:
        pdf_path.relative_to(bundle)
    except ValueError as exc:
        raise BundleError("Crop source PDF must be inside the bundle") from exc
    if not pdf_path.is_file():
        raise BundleError(f"Crop source PDF does not exist: {source_pdf}")
    document = fitz.open(pdf_path)
    if args.page < 1 or args.page > document.page_count:
        document.close()
        raise BundleError("Crop page is outside the PDF")
    page = document[args.page - 1]
    rect = fitz.Rect(*args.bbox)
    if rect.is_empty or rect.is_infinite or not page.rect.contains(rect):
        document.close()
        raise BundleError(f"Crop box must be within page bounds {tuple(page.rect)}")
    output = bundle / "figures" / "selected" / (args.output_name or safe_selected_name(args.figure_id, ".png"))
    output.parent.mkdir(parents=True, exist_ok=True)
    pixmap = page.get_pixmap(matrix=fitz.Matrix(args.dpi / 72.0, args.dpi / 72.0), clip=rect, alpha=False)
    pixmap.save(output)
    document.close()
    record = {
        "figure_id": args.figure_id,
        "file": relative_posix(output, bundle),
        "page": args.page,
        "caption": args.caption,
        "source_type": args.source_type,
        "source_pdf": source_pdf.replace("\\", "/"),
        "method": "page_crop",
        "crop_box_pdf_points": [float(value) for value in args.bbox],
        "sha256": sha256_file(output),
    }
    add_figure_record(manifest, record, args.replace)
    manifest["blog"]["approved_content_hash"] = None
    manifest["status"] = "prepared"
    manifest["updated_at"] = utc_now()
    atomic_json(bundle / "manifest.json", manifest)
    print(json.dumps(record, ensure_ascii=False))


def register_figure(args: argparse.Namespace) -> None:
    bundle = args.bundle.resolve()
    manifest = load_manifest(bundle)
    requested_source_pdf = getattr(args, "source_pdf", None)
    if args.source_type == "supplement" and not requested_source_pdf:
        raise BundleError("Supplement figures require --source-pdf")
    source_pdf = requested_source_pdf or manifest["paper"]["local_pdf"]
    source_pdf_path = (bundle / source_pdf).resolve()
    try:
        source_pdf_path.relative_to(bundle)
    except ValueError as exc:
        raise BundleError("Figure source PDF must be inside the bundle") from exc
    if not source_pdf_path.is_file():
        raise BundleError(f"Figure source PDF does not exist: {source_pdf}")
    source = args.file.resolve()
    try:
        source.relative_to(bundle)
    except ValueError as exc:
        raise BundleError("Registered images must already be inside the bundle") from exc
    if not source.is_file():
        raise BundleError(f"Figure file does not exist: {source}")
    suffix = source.suffix or mimetypes.guess_extension(mimetypes.guess_type(source.name)[0] or "") or ".png"
    output = bundle / "figures" / "selected" / (args.output_name or safe_selected_name(args.figure_id, suffix))
    output.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != output.resolve():
        shutil.copy2(source, output)
    record = {
        "figure_id": args.figure_id,
        "file": relative_posix(output, bundle),
        "page": args.page,
        "caption": args.caption,
        "source_type": args.source_type,
        "source_pdf": source_pdf.replace("\\", "/"),
        "method": "embedded",
        "crop_box_pdf_points": None,
        "sha256": sha256_file(output),
    }
    add_figure_record(manifest, record, args.replace)
    manifest["blog"]["approved_content_hash"] = None
    manifest["status"] = "prepared"
    manifest["updated_at"] = utc_now()
    atomic_json(bundle / "manifest.json", manifest)
    print(json.dumps(record, ensure_ascii=False))


class ImageSrcParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            return
        values = {key.lower(): value for key, value in attrs if value is not None}
        if values.get("src"):
            self.sources.append(values["src"])


def article_image_references(markdown: str, html_text: str) -> list[str]:
    refs = re.findall(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)", markdown)
    parser = ImageSrcParser()
    parser.feed(html_text)
    refs.extend(parser.sources)
    return sorted(set(unquote(ref.strip().strip("<>")) for ref in refs))


def compute_content_hash(bundle: Path, manifest: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for name in (manifest["blog"]["article_markdown"], manifest["blog"]["article_html"]):
        path = bundle / name
        digest.update(name.encode("utf-8"))
        digest.update(path.read_bytes())
    stable_figures = [
        {
            "figure_id": item.get("figure_id"),
            "file": item.get("file"),
            "page": item.get("page"),
            "caption": item.get("caption"),
            "source_type": item.get("source_type"),
            "source_pdf": item.get("source_pdf"),
            "method": item.get("method"),
            "crop_box_pdf_points": item.get("crop_box_pdf_points"),
            "sha256": item.get("sha256"),
        }
        for item in manifest.get("figures", [])
    ]
    digest.update(json.dumps(stable_figures, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    digest.update(str(manifest.get("paper", {}).get("sha256", "")).encode("ascii", errors="ignore"))
    return digest.hexdigest()


def validate_bundle(bundle: Path, *, write_approval: bool) -> dict[str, Any]:
    bundle = bundle.resolve()
    manifest = load_manifest(bundle)
    errors: list[str] = []
    warnings: list[str] = []
    paper = bundle / manifest.get("paper", {}).get("local_pdf", "")
    if not paper.is_file() or sha256_file(paper) != manifest.get("paper", {}).get("sha256"):
        errors.append("Source PDF is missing or its SHA-256 changed")
    for supplement in manifest.get("supplements", []):
        supplement_path = bundle / supplement.get("local_pdf", "")
        if not supplement_path.is_file() or sha256_file(supplement_path) != supplement.get("sha256"):
            errors.append(f"Supplement PDF is missing or changed: {supplement.get('source_id', '?')}")
    article_md = bundle / manifest.get("blog", {}).get("article_markdown", "article.md")
    article_html = bundle / manifest.get("blog", {}).get("article_html", "article.html")
    preview = bundle / manifest.get("blog", {}).get("preview", "preview.md")
    for path in (article_md, article_html, preview):
        if not path.is_file() or path.stat().st_size < 40:
            errors.append(f"Required article file is missing or empty: {path.name}")
    markdown = article_md.read_text(encoding="utf-8") if article_md.is_file() else ""
    html_text = article_html.read_text(encoding="utf-8") if article_html.is_file() else ""
    if "{{" in markdown or "Generate from the approved Markdown" in html_text:
        errors.append("Article still contains scaffold placeholders")
    if not manifest.get("blog", {}).get("title"):
        heading = re.search(r"^#\s+(.+)$", markdown, flags=re.MULTILINE)
        if heading:
            manifest["blog"]["title"] = heading.group(1).strip()
        else:
            errors.append("Blog title is missing")

    registered: dict[str, dict[str, Any]] = {}
    for figure in manifest.get("figures", []):
        required = ("figure_id", "file", "page", "caption", "source_type", "method", "sha256")
        missing = [key for key in required if figure.get(key) in (None, "")]
        if missing:
            errors.append(f"Figure record is incomplete ({figure.get('figure_id', '?')}): {', '.join(missing)}")
            continue
        path = (bundle / figure["file"]).resolve()
        try:
            path.relative_to(bundle)
        except ValueError:
            errors.append(f"Figure escapes the bundle: {figure['file']}")
            continue
        if not path.is_file():
            errors.append(f"Registered figure is missing: {figure['file']}")
            continue
        if sha256_file(path) != figure["sha256"]:
            errors.append(f"Registered figure changed after approval: {figure['file']}")
        if figure.get("source_type") not in {"main", "supplement"}:
            errors.append(f"Invalid figure source type: {figure.get('source_type')}")
        if figure.get("method") not in {"embedded", "page_crop"}:
            errors.append(f"Invalid figure extraction method: {figure.get('method')}")
        source_pdf = figure.get("source_pdf") or manifest.get("paper", {}).get("local_pdf")
        if not source_pdf or not (bundle / source_pdf).is_file():
            errors.append(f"Figure source PDF is missing: {figure.get('figure_id')}")
        registered[relative_posix(path, bundle)] = figure
    if not registered:
        errors.append("No source-paper figures are registered")
    elif len(registered) < 6:
        warnings.append("Fewer than six figures are registered; this is acceptable only when the paper has fewer useful figures")
    elif len(registered) > 10:
        warnings.append("More than ten figures are registered; confirm each one materially helps the explanation")

    references = article_image_references(markdown, html_text)
    referenced_local: set[str] = set()
    for reference in references:
        parsed = urlparse(reference)
        if parsed.scheme or reference.startswith("//") or reference.startswith("data:"):
            errors.append(f"Article contains a non-local image: {reference}")
            continue
        path = (bundle / reference).resolve()
        try:
            rel = relative_posix(path, bundle)
        except ValueError:
            errors.append(f"Article image escapes the bundle: {reference}")
            continue
        referenced_local.add(rel)
        if rel not in registered:
            errors.append(f"Article image is not registered in manifest.json: {reference}")
    unused = sorted(set(registered) - referenced_local)
    if unused:
        errors.append("Registered figures are not referenced by the article: " + ", ".join(unused))

    content_hash = None
    if not errors:
        content_hash = compute_content_hash(bundle, manifest)
        if write_approval:
            manifest["blog"]["approved_content_hash"] = content_hash
            manifest["status"] = "preview_ready"
            manifest["updated_at"] = utc_now()
            atomic_json(bundle / "manifest.json", manifest)
            publication_path = bundle / "publication.json"
            publication = json.loads(publication_path.read_text(encoding="utf-8"))
            publication["approved_content_hash"] = content_hash
            publication["updated_at"] = utc_now()
            atomic_json(publication_path, publication)
    return {"ok": not errors, "errors": errors, "warnings": warnings, "content_hash": content_hash}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Acquire a PDF and create a source bundle")
    prepare.add_argument("source")
    prepare.add_argument("--bundle", type=Path, required=True)
    prepare.add_argument("--dpi", type=int, default=144)

    supplement = subparsers.add_parser("add-supplement", help="Acquire and index an official supplementary PDF")
    supplement.add_argument("source")
    supplement.add_argument("--bundle", type=Path, required=True)
    supplement.add_argument("--dpi", type=int, default=144)

    crop = subparsers.add_parser("crop", help="Create and register a lossless page crop")
    crop.add_argument("--bundle", type=Path, required=True)
    crop.add_argument("--page", type=int, required=True)
    crop.add_argument("--bbox", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"), required=True)
    crop.add_argument("--figure-id", required=True)
    crop.add_argument("--caption", required=True)
    crop.add_argument("--source-type", choices=("main", "supplement"), default="main")
    crop.add_argument("--source-pdf", help="Bundle-relative source PDF; required for supplements")
    crop.add_argument("--output-name")
    crop.add_argument("--dpi", type=int, default=200)
    crop.add_argument("--replace", action="store_true")

    register = subparsers.add_parser("register", help="Register an extracted source-paper image")
    register.add_argument("--bundle", type=Path, required=True)
    register.add_argument("--file", type=Path, required=True)
    register.add_argument("--page", type=int, required=True)
    register.add_argument("--figure-id", required=True)
    register.add_argument("--caption", required=True)
    register.add_argument("--source-type", choices=("main", "supplement"), default="main")
    register.add_argument("--source-pdf", help="Bundle-relative source PDF; required for supplements")
    register.add_argument("--output-name")
    register.add_argument("--replace", action="store_true")

    validate = subparsers.add_parser("validate", help="Validate provenance and approve the local preview")
    validate.add_argument("--bundle", type=Path, required=True)
    validate.add_argument("--check-only", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            if args.dpi < 72 or args.dpi > 300:
                raise BundleError("DPI must be between 72 and 300")
            prepare_bundle(args.source, args.bundle.resolve(), args.dpi)
        elif args.command == "add-supplement":
            if args.dpi < 72 or args.dpi > 300:
                raise BundleError("DPI must be between 72 and 300")
            add_supplement(args.source, args.bundle.resolve(), args.dpi)
        elif args.command == "crop":
            crop_figure(args)
        elif args.command == "register":
            register_figure(args)
        elif args.command == "validate":
            result = validate_bundle(args.bundle, write_approval=not args.check_only)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ok"] else 2
        return 0
    except (BundleError, requests.RequestException, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
