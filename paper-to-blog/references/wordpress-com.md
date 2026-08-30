# WordPress.com draft workflow

Read this only for WordPress setup or draft upload.

## First-time setup

1. Create a free WordPress.com site. The free plan uses a `.wordpress.com` address and has limited media storage.
2. Follow WordPress.com's official OAuth/application process to obtain an access token with permission to create posts and media.
3. Set these environment variables outside the skill and project:

   - `PAPER_BLOG_WP_SITE`: WordPress.com site ID or domain.
   - `PAPER_BLOG_WP_TOKEN`: OAuth bearer token.

Never paste the token into `manifest.json`, `publication.json`, source files, shell history, screenshots, or chat.

Official documentation:

- https://developer.wordpress.com/docs/api/
- https://developer.wordpress.com/docs/api/getting-started/
- https://wordpress.com/support/plan-features/

## Upload behavior

- Run bundle validation immediately before the adapter.
- Upload only registered images referenced by `article.html`.
- Reuse an uploaded media item when its recorded SHA-256 matches.
- Create terms as needed, then create or update one post with `status=draft`.
- Save state after each successful media upload so retries can resume.
- Never delete old media or posts automatically.
- If quota information is available and the new upload would leave less than 5% or 50 MB free, whichever is larger, stop before uploading.
- If quota information is unavailable, report that fact and rely on the service response; do not claim capacity was checked.

The adapter has no public-publish option. Any future publishing workflow must be a separate, explicitly authorized change.
