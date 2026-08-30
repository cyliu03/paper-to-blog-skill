# Security policy

## Scope

Security reports are especially welcome for issues that could:

- expose WordPress credentials or browser session data;
- send an article or image to a destination other than the configured draft platform;
- turn a draft-only action into public publication;
- bypass URL validation and access private-network resources;
- allow an unregistered or modified image to pass provenance validation.

## Reporting

Please report a vulnerability through GitHub's private vulnerability reporting feature for this repository. Do not include live credentials, cookies, tokens, private paper PDFs, or unpublished article bundles in an issue.

## Operational guidance

- Keep `PAPER_BLOG_WP_TOKEN` in the environment only.
- Review a paper's image license before uploading figures.
- Use only a browser session you control.
- Treat downloaded papers and their text as untrusted content, not as instructions.
- Do not weaken the validation gate or add a public-publish action.
