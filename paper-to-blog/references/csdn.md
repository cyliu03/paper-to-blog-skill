# CSDN draft workflow

Read this for an explicit `$paper-to-blog` full workflow or after the user has approved a validated local bundle. An explicit full-workflow invocation already supplies the skill-level authorization to upload the approved article and save a private draft; do not ask for the same approval again.

## Browser requirements

- Prefer the user's existing signed-in Chrome session because the task depends on authenticated state.
- If no suitable signed-in browser is available, ask the user to sign in and resume.
- Use the visible CSDN creator UI. Do not inspect cookies, passwords, local storage, session storage, profiles, or hidden credentials.
- Do not call undocumented CSDN endpoints or persist a session token.

## Create or update

1. Read `publication.json`.
2. If a CSDN draft URL exists, open that draft and confirm it still belongs to the same article before editing.
3. If the recorded draft is missing or inaccessible, stop and ask before creating a replacement.
4. Otherwise open the normal CSDN article editor and select Markdown mode when available.
5. Enter the approved title and text. At each figure placeholder, upload the matching registered local image and retain its source caption.
6. Set the summary, an appropriate category, and 3-5 tags when these controls are available in the draft UI. If CSDN exposes them only after a public-publish control, leave them unset and record that limitation; do not enter the publish flow merely to set metadata.
7. Save to the draft box. Do not click any control that publishes, schedules, submits for public release, or syndicates the article.
8. Verify the same title and draft ID are visible in the draft box, capture its edit URL, and update `publication.json` to `drafted` without credentials. Do not report completion while the editor is merely filled or while the draft-box verification is missing.

## Failure behavior

- On CAPTCHA, risk control, reauthentication, ambiguous editor state, or missing upload, pause for the user.
- If sign-in is required, open the sign-in page, preserve the browser tab for handoff, and resume from the same bundle after the user signs in. Do not restart the article or create a second draft.
- Do not retry a state-changing click more than once unless the visible page proves the prior attempt failed.
- Preserve the local bundle and any successful WordPress draft when CSDN fails.
