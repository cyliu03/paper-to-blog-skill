#!/usr/bin/env python3
"""Create or update one WordPress.com draft from an approved article bundle."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from paper_assets import BundleError, atomic_json, compute_content_hash, load_manifest, sha256_file, utc_now, validate_bundle


DEFAULT_API_BASE = "https://public-api.wordpress.com/wp/v2/sites/{site}"
DEFAULT_SITE_INFO = "https://public-api.wordpress.com/rest/v1.1/sites/{site}"
MIN_FREE_BYTES = 50 * 1024 * 1024


class WordPressError(RuntimeError):
    pass


class NotConfiguredError(WordPressError):
    pass


class WordPressClient:
    def __init__(self, site: str, token: str, api_base: str, site_info_url: str, timeout: int = 60) -> None:
        safe_site = quote(site, safe="")
        self.base = api_base.format(site=safe_site).rstrip("/")
        self.site_info_url = site_info_url.format(site=safe_site)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}", "User-Agent": "paper-to-blog/1.0"})

    def _json(self, response: requests.Response) -> Any:
        try:
            data = response.json()
        except ValueError as exc:
            raise WordPressError(f"WordPress returned a non-JSON response ({response.status_code})") from exc
        if response.status_code >= 400:
            message = data.get("message") if isinstance(data, dict) else None
            raise WordPressError(f"WordPress request failed ({response.status_code}): {message or 'unknown error'}")
        return data

    def site_info(self) -> dict[str, Any] | None:
        response = self.session.get(self.site_info_url, timeout=self.timeout)
        if response.status_code in {401, 403, 404}:
            return None
        data = self._json(response)
        return data if isinstance(data, dict) else None

    def upload_media(self, path: Path, alt_text: str, caption: str) -> dict[str, Any]:
        with path.open("rb") as stream:
            response = self.session.post(
                f"{self.base}/media",
                files={"file": (path.name, stream)},
                data={"alt_text": alt_text, "caption": caption},
                timeout=self.timeout,
            )
        data = self._json(response)
        media_id = data.get("id") or data.get("ID")
        source_url = data.get("source_url") or data.get("URL") or data.get("url")
        if media_id is None or not source_url:
            raise WordPressError("WordPress media response omitted its ID or URL")
        return {"id": media_id, "url": source_url}

    def ensure_term(self, kind: str, name: str) -> int:
        endpoint = "categories" if kind == "category" else "tags"
        response = self.session.get(f"{self.base}/{endpoint}", params={"search": name, "per_page": 100}, timeout=self.timeout)
        data = self._json(response)
        items = data if isinstance(data, list) else data.get(endpoint, []) if isinstance(data, dict) else []
        for item in items:
            if str(item.get("name", "")).casefold() == name.casefold():
                return int(item["id"])
        created = self._json(self.session.post(f"{self.base}/{endpoint}", json={"name": name}, timeout=self.timeout))
        if "id" not in created:
            raise WordPressError(f"WordPress did not return an ID for {kind}: {name}")
        return int(created["id"])

    def save_draft(self, payload: dict[str, Any], post_id: int | None) -> dict[str, Any]:
        if payload.get("status") != "draft":
            raise WordPressError("Adapter invariant failed: only draft status is allowed")
        endpoint = f"{self.base}/posts/{post_id}" if post_id else f"{self.base}/posts"
        data = self._json(self.session.post(endpoint, json=payload, timeout=self.timeout))
        if "id" not in data:
            raise WordPressError("WordPress post response omitted its ID")
        return data


def read_publication(bundle: Path) -> dict[str, Any]:
    path = bundle / "publication.json"
    if not path.is_file():
        raise BundleError("Missing publication.json")
    return json.loads(path.read_text(encoding="utf-8"))


def write_publication(bundle: Path, publication: dict[str, Any]) -> None:
    publication["updated_at"] = utc_now()
    atomic_json(bundle / "publication.json", publication)


def extract_quota(info: dict[str, Any] | None) -> tuple[int, int] | None:
    if not info:
        return None
    quota = info.get("quota_space")
    if not isinstance(quota, dict):
        return None
    allowed = quota.get("bytes_allowed")
    used = quota.get("bytes_used")
    if isinstance(allowed, (int, float)) and isinstance(used, (int, float)) and allowed > 0 and used >= 0:
        return int(allowed), int(used)
    return None


def replace_local_image_urls(html_text: str, media: dict[str, dict[str, Any]]) -> str:
    pattern = re.compile(r"(?P<prefix>\bsrc\s*=\s*)(?P<quote>[\"'])(?P<value>[^\"']+)(?P=quote)", re.IGNORECASE)

    def replace(match: re.Match[str]) -> str:
        value = match.group("value").replace("\\", "/")
        record = media.get(value)
        if not record:
            return match.group(0)
        return f"{match.group('prefix')}{match.group('quote')}{record['url']}{match.group('quote')}"

    return pattern.sub(replace, html_text)


def update_failure(bundle: Path, message: str) -> None:
    publication = read_publication(bundle)
    wordpress = publication.setdefault("wordpress", {})
    wordpress["status"] = "failed"
    wordpress["last_error"] = message
    write_publication(bundle, publication)


def run(args: argparse.Namespace) -> dict[str, Any]:
    bundle = args.bundle.resolve()
    manifest = load_manifest(bundle)
    validation = validate_bundle(bundle, write_approval=False)
    if not validation["ok"]:
        raise BundleError("Bundle validation failed: " + "; ".join(validation["errors"]))
    current_hash = compute_content_hash(bundle, manifest)
    approved_hash = manifest.get("blog", {}).get("approved_content_hash")
    publication = read_publication(bundle)
    if not approved_hash or current_hash != approved_hash or publication.get("approved_content_hash") != approved_hash:
        raise BundleError("Bundle changed after preview approval; validate and obtain approval again")

    site = os.environ.get("PAPER_BLOG_WP_SITE", "").strip()
    token = os.environ.get("PAPER_BLOG_WP_TOKEN", "").strip()
    if not site or not token:
        wordpress = publication.setdefault("wordpress", {})
        wordpress["status"] = "not_configured"
        wordpress["last_error"] = "Set PAPER_BLOG_WP_SITE and PAPER_BLOG_WP_TOKEN"
        write_publication(bundle, publication)
        raise NotConfiguredError("WordPress.com is not configured; set PAPER_BLOG_WP_SITE and PAPER_BLOG_WP_TOKEN")

    client = WordPressClient(site, token, args.api_base, args.site_info_url, args.timeout)
    figures = {item["file"].replace("\\", "/"): item for item in manifest.get("figures", [])}
    html_path = bundle / manifest["blog"]["article_html"]
    html_text = html_path.read_text(encoding="utf-8")
    referenced = [path for path in figures if re.search(rf"\bsrc\s*=\s*[\"']{re.escape(path)}[\"']", html_text, re.IGNORECASE)]
    upload_bytes = sum((bundle / path).stat().st_size for path in referenced)

    quota = None if args.dry_run else extract_quota(client.site_info())
    quota_status: dict[str, Any]
    if quota:
        allowed, used = quota
        minimum_free = max(MIN_FREE_BYTES, int(allowed * 0.05))
        remaining_after = allowed - used - upload_bytes
        quota_status = {"checked": True, "allowed_bytes": allowed, "used_bytes": used, "remaining_after_bytes": remaining_after}
        if remaining_after < minimum_free:
            raise WordPressError("Media upload would leave less than the configured WordPress free-space reserve")
    else:
        quota_status = {"checked": False, "reason": "The site API did not expose byte quota fields"}

    wordpress = publication.setdefault("wordpress", {})
    wordpress["site"] = site
    wordpress.setdefault("media", {})
    media_state: dict[str, dict[str, Any]] = wordpress["media"]
    for path in referenced:
        figure = figures[path]
        existing = media_state.get(path)
        if existing and existing.get("sha256") == figure["sha256"] and existing.get("url"):
            continue
        if args.dry_run:
            media_state[path] = {"id": f"dry-run-{len(media_state) + 1}", "url": f"https://example.invalid/{Path(path).name}", "sha256": figure["sha256"]}
        else:
            uploaded = client.upload_media(bundle / path, figure["figure_id"], figure["caption"])
            media_state[path] = {**uploaded, "sha256": figure["sha256"]}
            wordpress["status"] = "pending"
            wordpress["last_error"] = None
            write_publication(bundle, publication)

    content = replace_local_image_urls(html_text, media_state)
    categories = manifest.get("blog", {}).get("categories") or []
    tags = manifest.get("blog", {}).get("tags") or []
    if args.dry_run:
        category_ids = list(range(100, 100 + len(categories)))
        tag_ids = list(range(200, 200 + len(tags)))
    else:
        category_ids = [client.ensure_term("category", item) for item in categories]
        tag_ids = [client.ensure_term("tag", item) for item in tags]
    payload: dict[str, Any] = {
        "title": manifest["blog"]["title"],
        "content": content,
        "excerpt": manifest["blog"].get("summary", ""),
        "status": "draft",
        "categories": category_ids,
        "tags": tag_ids,
    }
    post_id = wordpress.get("post_id")
    if args.dry_run:
        post = {"id": post_id or 999, "link": "https://example.invalid/draft", "status": "draft"}
    else:
        post = client.save_draft(payload, int(post_id) if post_id else None)
    if post.get("status") not in {None, "draft"}:
        raise WordPressError("WordPress returned a non-draft post state")
    wordpress.update(
        {
            "status": "draft",
            "post_id": int(post["id"]),
            "edit_url": post.get("link") or f"https://wordpress.com/post/{quote(site, safe='')}/{post['id']}",
            "last_error": None,
            "quota": quota_status,
            "content_hash": approved_hash,
        }
    )
    write_publication(bundle, publication)
    return {"status": "draft", "post_id": wordpress["post_id"], "edit_url": wordpress["edit_url"], "dry_run": args.dry_run}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help=argparse.SUPPRESS)
    parser.add_argument("--site-info-url", default=DEFAULT_SITE_INFO, help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    bundle = args.bundle.resolve()
    try:
        result = run(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except NotConfiguredError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (BundleError, WordPressError, requests.RequestException, OSError, ValueError, json.JSONDecodeError) as exc:
        try:
            update_failure(bundle, str(exc))
        except Exception:
            pass
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
