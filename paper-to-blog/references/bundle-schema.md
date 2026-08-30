# Bundle schema

The bundle directory is the canonical record for one paper article.

```text
bundle/
|-- article.md
|-- article.html
|-- preview.md
|-- manifest.json
|-- publication.json
|-- source/
|   |-- paper.pdf
|   |-- source.json
|   |-- text.txt
|   `-- pages/page-0001.png
`-- figures/
    |-- extracted/
    `-- selected/
```

## `manifest.json`

- `schema_version`: currently `1`.
- `paper`: input, canonical URL, local PDF, SHA-256, page count, and PDF metadata.
- `figure_candidates`: mechanically extracted candidates; these are not approved for publication.
- `figures`: registered source-paper figures approved for the article.
- `blog`: title, summary, categories, tags, language, article paths, and approved content hash.
- `status`: `prepared`, `preview_ready`, or `approved_for_draft_upload`.

The validation command sets the approved content hash only after the local article passes. Upload requires the hash to match the current Markdown, HTML, manifest figure records, and figure files.

## `publication.json`

Store no credentials. Keep only:

- WordPress site, post ID, edit URL, status, uploaded media IDs/URLs/hashes, and last error.
- CSDN draft URL, status, last update time, and last error.
- local approved content hash.

Valid platform states are `not_configured`, `pending`, `draft`, and `failed`. Public `published` state is outside this skill.
