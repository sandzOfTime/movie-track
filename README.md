# movie-track

Import cinema listing images into SQLite and send alerts when a tracked movie has
a future showtime in a preferred format (IMAX, 4DX, XS3, etc.). A vision model
performs OCR and structured extraction; Python handles matching and delivery.
FastAPI exposes the operations and a CLI runs the same bounded jobs from cron.
Email via Resend is the default notification provider.

## Setup

Requires Python 3.11+. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/pip install -e . --no-deps
.venv/bin/pytest -q
.venv/bin/uvicorn movie_track.api:app --host 127.0.0.1 --port 8000
```

Export configuration using your shell or process manager; `.env.example` lists
variable names but is not automatically loaded. Never commit credentials.

- `MOVIE_TRACK_API_TOKEN`: private bearer token for API access.
- `MOVIE_TRACK_DATA`: SQLite/image directory, default `var` relative to the working
  directory. Use a persistent absolute path in deployment.
- `LISTING_ALLOWED_HOSTS`: exact comma-separated cinema and image-CDN hosts.
- `MOVIE_TRACK_OCR_API_KEY` (or `OPENAI_API_KEY`): OpenAI credential.
- `OCR_MODEL`: defaults to `gpt-4.1-mini`.
- `RESEND_API_KEY` and `EMAIL_FROM`: Resend credential and verified sender address.

All endpoints except `GET /health` require `Authorization: Bearer <token>`.
Without a configured API token, protected endpoints return 503. Keep the API
private; public deployment also needs HTTPS and request/rate limits.

## Import listings

`POST /listings/import` accepts the body in [examples/fusion-import.json](examples/fusion-import.json):

```json
{
  "source_url": "https://www.fusionsuperplex.co/film-schedule-page/",
  "timezone": "America/Nassau",
  "context": "Cinema location: Fusion Superplex, Nassau, The Bahamas. Theater type means format, including IMAX, 4DX and XS3."
}
```

You can supply an optional `image_urls` array of explicit poster URLs. Otherwise,
the importer discovers ordinary HTML `img src` images. Requests require HTTPS,
check redirect hosts, and limit downloads to 15 MiB per file and 20 images per
import. JavaScript pages, lazy-loaded images, PDFs, and source-specific image
selection need an adapter or explicit image URLs. Only allow trusted public hosts;
the host allowlist is not a DNS-rebinding firewall. Deployment network policy is
configured separately.

Images and supplied context are sent to OpenAI. Use context for known source
facts, especially poster dates. The extraction prompt requests omission of
ambiguous facts, but OCR can still be inaccurate: review `GET /listings` before
sending real alerts.

Each successful nonempty extraction atomically becomes the source's latest
snapshot. Keep `source_url` stable across refreshes. Different source URLs coexist;
older snapshots remain stored but are excluded from matching. Failed or empty
extraction preserves the previous snapshot. Empty extraction is treated as
suspicious, so this version cannot confirm automatic removal of all shows.

Showtimes must have UTC offsets and are stored in UTC; rating, runtime, language,
date range and details are stored as JSON metadata. Duplicate showtimes within
one import are collapsed. Downloaded images are retained by content hash.
Retention cleanup is not yet implemented.

## Check and alert

`POST /alerts/check` accepts the body in [examples/email-alert.json](examples/email-alert.json):

```json
{
  "movie": "Dune",
  "theater_type": "IMAX",
  "cinema": "Fusion Superplex",
  "channel": "email",
  "recipient": "you@example.com",
  "dry_run": true
}
```

`theater_type` means format; `cinema` optionally restricts location. Matching uses
exact titles and formats while ignoring case and repeated whitespace. Only future
showtimes from the latest successful snapshot per source qualify. Each email
includes the particular showtime and source. Tracking preferences live in your
cron request JSON; there is no subscription-management endpoint yet.

The response reports matching showtimes, sent count, and already-sent count.
Dry runs are the default and never send or reserve a delivery. Set `dry_run` to
`false` explicitly to send. Delivery records suppress repeated alerts for the
same recipient/channel/movie/cinema/format/showtime, even after reimport. SQLite
serializes concurrent checks. A timeout after provider acceptance or a crash
before committing can still cause duplicate delivery on retry; this is not
exactly-once delivery. Provider acceptance does not guarantee receipt. A failed
send stops the job; earlier successful deliveries remain recorded.

Optional providers are retained for future use:

- Set `EMAIL_PROVIDER=smtp` to use SMTP with mandatory STARTTLS. Configure
  `SMTP_HOST`, `SMTP_PORT` (587 by default), `SMTP_FROM`, and optional
  `SMTP_USERNAME`/`SMTP_PASSWORD`.
- `channel=whatsapp` uses Twilio's free-form API. Set `TWILIO_ACCOUNT_SID`,
  `TWILIO_AUTH_TOKEN` and `TWILIO_WHATSAPP_FROM`; sender and recipient must use
  `whatsapp:+...` addresses. This works only within the allowed active conversation
  window or sandbox. Unattended business-initiated WhatsApp alerts generally need
  approved templates; template sending is not implemented. Use opted-in recipients.

## Cron

Store private request JSON outside the repo and load credentials securely into
the job environment. Example schedules (timezone is configured on the host):

```cron
0 9 * * * cd /workspace/movie-track && .venv/bin/movie-track import /secure/import.json >> /var/log/movie-track-import.log 2>&1
10 9 * * * cd /workspace/movie-track && .venv/bin/movie-track alert /secure/alert.json >> /var/log/movie-track-alert.log 2>&1
```

The CLI prints JSON and exits nonzero on failure. Import and alert are separate
jobs; alert checks can therefore use stale listings after a failed refresh.
Monitor job failures. A maximum snapshot-age policy is not yet implemented.
Use a persistent host or managed job runner; development environment processes
and cron jobs should not be assumed to survive a new task.

## Validation and live setup

Tests cover mocked page/image import, structured vision output, snapshot
replacement, failed extraction preservation, matching, delivery retries,
deduplication, Resend requests, redirect restrictions, and API authentication.
They do not establish live OCR accuracy or email delivery.

The Fusion page has not been inspected successfully: the development environment
proxy blocked its destination. Automatic image discovery is tested against
fixtures, but actual Fusion poster selection remains unverified. See
[docs/environment-settings.md](docs/environment-settings.md) for required live
configuration. No real messages are sent by the tests.
