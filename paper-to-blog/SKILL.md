---
name: paper-to-blog
description: Turn computer science, AI, and brain-computer-interface papers into traceable Chinese deep-reading blog bundles using only source-paper figures. An explicit $paper-to-blog invocation normally continues through a verified CSDN draft; implicit paper-reading requests remain local-preview only.
---

# Paper to Blog

Create a traceable local article bundle first. Treat that bundle as the canonical record; platform drafts are derived copies.

## Choose the workflow

- When the user explicitly invokes `$paper-to-blog` with a paper source, run **Preview**, then continue through **Upload drafts** by default. The required terminal outcome is a CSDN draft saved and verified in the draft box, unless login, CAPTCHA, risk control, validation failure, or platform failure blocks it.
- Treat the explicit invocation as authorization to upload the approved title, article text, and registered source-paper figures and to create or update private platform drafts. Do not ask for a second skill-level confirmation before filling or saving the draft. Comply with any confirmation that the browser host itself requires.
- When the user explicitly says `仅生成预览`, `本地预览`, or `不要上传`, run **Preview** only and stop locally.
- When the skill is selected implicitly from an ordinary natural-language paper-reading request, run **Preview** only. Implicit selection does not authorize external uploads.
- For `$paper-to-blog 确认上传草稿 BUNDLE`, skip regeneration and run **Upload drafts** on that validated bundle.
- Never publish publicly. This skill creates or updates drafts only.

## Preview

1. Read [references/writing-standard.md](references/writing-standard.md) and [references/figure-provenance.md](references/figure-provenance.md).
2. Resolve the source legally. For an inaccessible or paywalled full text, stop and ask the user to attach the PDF. Do not bypass access controls.
3. Choose the article root in this order: a location supplied by the user, the
   `PAPER_BLOG_ROOT` environment variable, or `articles/` in the current
   workspace. Create `ROOT/YYYY-MM-DD-slug/` and run:

   ```text
   python scripts/paper_assets.py prepare SOURCE --bundle BUNDLE
   ```

   When an official supplementary PDF is available, add it with `paper_assets.py add-supplement SUPPLEMENT --bundle BUNDLE`.

4. Inspect every rendered page visually. Use extracted candidates when they faithfully contain the complete figure. For vector or composite figures, use the script's `crop` command with the figure's page bounding box.
5. Register each selected figure. Normally select 6-10 useful figures, using fewer when the paper contains fewer. Never duplicate images to meet a quota.
6. Write `article.md` and `article.html` in Chinese, normally 4,000-6,000 Chinese characters. Preserve the English title, important English terms, figure labels, DOI, and references.
7. Write `preview.md`, then run `paper_assets.py validate`. Fix every reported provenance or image-reference error.
8. Show or record the local preview and summarize unresolved uncertainties. In explicit full-workflow mode, continue directly to **Upload drafts**; in preview-only mode, stop here.

## Upload drafts

Read [references/wordpress-com.md](references/wordpress-com.md) and [references/csdn.md](references/csdn.md).

1. Re-run bundle validation. Refuse upload if validation fails or the approved content hash changed.
2. If WordPress is configured, run `scripts/wordpress_draft.py --bundle BUNDLE`. It may only send `status=draft`. If WordPress is not configured, continue with CSDN and report the missing archive destination.
3. Use a connected, signed-in browser for CSDN. Use the visible editor UI only; do not inspect or export cookies, passwords, local storage, or session data, and do not call undocumented CSDN endpoints.
4. Upload every registered article image, replace local image paths with the resulting CSDN image URLs, save the CSDN draft, and verify the title and images in the editor.
5. Open the CSDN draft box and confirm that the same title and draft ID are present. Record the edit URL and `drafted` status in `publication.json`. Filling the editor without saving and verifying the draft is incomplete.
6. Never click a public publish control. Set summary, category, and 3-5 tags only when the draft UI exposes them without entering a publish flow; otherwise preserve the saved draft and report that those fields remain for publication setup.
7. Preserve partial success. A later run resumes the failed platform. Update an existing draft rather than creating a duplicate; if the recorded CSDN draft is missing, ask before creating another.

## Non-negotiable rules

- Images must originate in the paper or its supplementary material. No generated, redrawn, reconstructed, AI-restored, decorative, or stock images.
- Faithful full-figure extraction and lossless subfigure crops are allowed. Do not add arrows, labels, watermarks, or other semantic changes.
- Separate observed results, author interpretation, and the blog author's evaluation.
- Cite every displayed figure with its original label, page, caption/source, and paper identifier.
- Keep the source PDF local. Do not upload the PDF to either platform.
- Keep credentials out of files and logs. WordPress reads only `PAPER_BLOG_WP_SITE` and `PAPER_BLOG_WP_TOKEN`.

## Resources

- Read [references/bundle-schema.md](references/bundle-schema.md) when creating, repairing, or validating a bundle.
- Use [assets/article-template.md](assets/article-template.md) as the initial article structure.
- Run `scripts/run_tests.py` and the Skill Creator quick validator after changing this skill.
