# Settings needed for live validation

Preserve existing network destinations and presets while adding:

- `www.fusionsuperplex.co` and `fusionsuperplex.co` for Fusion listings.
- `api.openai.com` for structured image extraction.
- `api.resend.com` for email notifications.

Provide `MOVIE_TRACK_OCR_API_KEY` securely (scoped to `api.openai.com` when using
proxy-injected credentials), and `RESEND_API_KEY` (scoped to `api.resend.com`).
Set `EMAIL_FROM` to a verified sender address, and configure
`LISTING_ALLOWED_HOSTS=www.fusionsuperplex.co,fusionsuperplex.co` in the process.
Additional image-CDN hosts may be needed after inspecting the actual page.
Set a private `MOVIE_TRACK_API_TOKEN` and persistent `MOVIE_TRACK_DATA` path.
Do not put credential values in Git or chat.

The earlier attempt to save these network requirements returned
`draft_not_editable`; no configuration change was confirmed. These notes do not
apply settings, publish the environment, or verify live access. The last live
Fusion request received HTTP 403 from the environment proxy before website HTML
was received.

After applying settings, retry the Fusion import, inspect extracted listings,
and run the alert example with `dry_run=true`. A real send requires explicit
`dry_run=false`. No real messages were sent during development.

Use the existing checkout in each isolated cloud task; do not create a Git
worktree unless explicitly requested. Running API processes and scheduled jobs
must be restarted when needed in a new task. See the README for startup commands.

SMTP is an optional alternative requiring outbound TCP access to the chosen mail
server. It cannot use an HTTPS-only proxy secret binding.
