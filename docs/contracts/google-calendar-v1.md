# Google Calendar booking contract — proposed v1

Status: **proposed for SNX-67 (FR-22)**. The product decisions marked *decided* were made by the Product Owner on
November 28, 2026. Items under [Open decisions](#open-decisions) still need team or client approval before the
dependent tickets claim acceptance. This document defines behavior; it does not claim the feature is implemented.

## Why calendar data

SolTech's prospects book through SolTech's web booking app, which hands off to Calendly, which writes the meeting into
the host's Google Calendar. The booking is therefore a lead signal as strong as a first email: someone chose a time to
talk. Ingesting it lets staff see, per lead, the meetings booked, moved and cancelled, and the next one coming up.

```
web booking app ──▶ Calendly ──▶ Google Calendar event (host = SolTech staff, attendee = invitee)
                                        │
                                        ▼  read-only, incremental
                      Google Workspace master ──▶ bronze.raw_calendar_events ──▶ dbt silver.meetings ──▶ API ──▶ dashboard
```

## Source and access

- **API:** Google Calendar API v3, `events.list` on one configured calendar (`GOOGLE_CALENDAR_ID`, default `primary`).
- **Scope:** `https://www.googleapis.com/auth/calendar.events.readonly`, the least privilege that reads events. No write
  scope, ever.
- **Account:** the same connected Google account as the Gmail mailbox. One OAuth token carries both scopes; adding
  Calendar means re-consenting once with both (the SNX-21 probe flow). `source_account_id` is that account's address,
  canonical lowercase, exactly as Gmail records it.
- **Recurring events** are read expanded (`singleEvents=true`): each occurrence is its own event with a stable ID, so a
  moved or cancelled occurrence is tracked like any single event.

## Selection (*decided*)

An event is ingested when at least one attendee's email domain is **not** in `GOOGLE_INTERNAL_DOMAINS` (SolTech's own
domains). Calendly bookings always list the invitee as an attendee, so they qualify; internal meetings, personal blocks
and events with no attendees are not stored. Organizer and room/resource attendees never count as external.

Once any version of an event has been stored, **every later version is stored**, even if it no longer qualifies (for
example, the invitee was removed). Otherwise silver would keep showing a stale version. A version that never qualified
is skipped and counted, not stored.

## Bronze: one row per event version

`bronze.raw_calendar_events` is append-only, like `bronze.raw_messages`, but its grain is **one version of one event**,
because calendar events change after they are created and messages do not.

| Field | Meaning |
|---|---|
| `source_channel` | `google_calendar` (lineage; identity resolution uses the email key below) |
| `source_account_id` | Connected Google account address, canonical lowercase |
| `source_calendar_id` | The calendar the event was read from |
| `source_event_id` | Google's event ID: stable across versions, unique within the calendar |
| `source_etag` | Google's version identifier for this event state |
| `source_updated_at` | Google's `updated` time for this version (UTC); orders versions |
| `event_status` | `confirmed`, `tentative` or `cancelled` as Google reported it |
| `external_participant_id` | The single external attendee's canonical email; null when there is not exactly one |
| `starts_at`, `ends_at`, `event_timezone` | Scheduled time; all-day events keep their date with a null time component recorded in `parsed_payload` |
| `ingested_at` | When SolNexus durably stored this version |
| `raw_payload` | The event JSON exactly as received |
| `parsed_payload` | Query aid derived from the payload (title, attendee list with response status, organizer, Calendly markers); not evidence |

**Uniqueness and replay.** The key is `(source_account_id, source_calendar_id, source_event_id, source_etag)`. The etag is
Google's own version identity, so a retried page that returns the same version stores nothing new
(`ON CONFLICT DO NOTHING`). Comparing raw bytes would be wrong here: Google may serialize the same version with
different key order, so byte equality is not version equality.

**Deletions.** Incremental sync reports a deleted or declined-by-organizer event as `status: cancelled`. It is stored
as one more version. Nothing is ever deleted from bronze; silver decides what a cancellation means.

**Quarantine.** An event that cannot be parsed or that PostgreSQL rejects is quarantined with a reason, as messages are,
so one bad event cannot block the cursor.

## Incremental sync

The cursor is Calendar's `nextSyncToken`, stored in `app.ingestion_checkpoints` under
`(google_calendar, <account>/<calendar>)` and saved **in the same transaction as the last page it covers**, the rule
every connector follows.

- **No checkpoint:** full sync, page by page, then save the sync token from the last page.
- **Checkpoint:** `events.list` with `syncToken` returns only events changed since, including cancellations.
- **`410 Gone`:** the token expired; run a full sync again. Replays are no-ops in bronze, so re-reading is safe, only
  slower.

Whether the first full sync can be bounded to a recent window (`GOOGLE_CALENDAR_BACKFILL_DAYS`) while still returning a
sync token is to be verified against the API in the extraction ticket. If it cannot, the full sync reads the whole
calendar and the selection rule keeps bronze small.

## Identity and resolution (*decided*)

A booking links to a clinic through the **same staff-confirmed email identity as Gmail**: the identity key of a calendar
event is `(gmail, <connected account address>, <external attendee email>)`. The calendar belongs to the same Google
account as the mailbox, and the identifier is the same email address, so one staff confirmation covers both. The
event keeps `source_channel = google_calendar` for lineage. This is the one exception to "a confirmation for one channel
does not verify another" in [the identity contract](phase1-identity-v1.md#calendar-events-fr-22); it does not extend
to any other channel.

Resolution is per **event**, not per version, with the same outcomes and review reasons as messages
(`linked`, `needs_review`; `no_match`, `unconfirmed_source_identity`, `incomplete_source_identity`, ...). If a later
version changes the external attendee, the event is resolved again under the new key. Mapping confirmations,
corrections and revocations re-evaluate calendar events for the exact key, in the same bounded, replay-safe batches
as messages.

**Inquiries (*decided*).** The first stored version of an event whose external attendee matches no known clinic opens a
**Clinic name unknown** inquiry, exactly as a first inbound email does. Because the inquiry is unique per open identity
key, an email and a booking from the same person join one inquiry instead of creating two. A clinic name typed into the
Calendly form is candidate evidence only; only staff confirmation supplies the name.

## Silver

`silver.meetings`: one row per calendar event, built from its **latest version** (highest `source_updated_at`, then
etag as a tie-break).

| Column | Meaning |
|---|---|
| `meeting_id` | Stable surrogate of `(source_account_id, source_calendar_id, source_event_id)` |
| `record_type`, `lead_id` | The linked clinic or open inquiry; null when unresolved |
| `status` | `scheduled`, `tentative` or `cancelled` |
| `starts_at`, `ends_at`, `event_timezone` | Latest scheduled time |
| `booked_at` | First stored version's `source_updated_at` (when the booking appeared) |
| `last_changed_at` | Latest version's `source_updated_at` |
| `reschedule_count` | Number of versions whose start time differs from the previous version's |
| `is_calendly` | Suggestion derived from Calendly markers in the payload; not evidence |
| `external_participant_id` | Latest version's external attendee |

`silver.leads` gains `next_meeting_at` (earliest linked, non-cancelled meeting starting after `published_at`) and
`last_meeting_at` (latest linked, non-cancelled meeting that has started). The same read-time link check as clinic
history applies: a meeting is shown under a clinic only while its resolution and the active mapping agree.

## API and dashboard

- `GET /api/v1/leads/{clinic_id}/meetings`: linked meetings, upcoming first then past by start time, with the same
  pagination and `published_at` metadata as history.
- Lead rows in `GET /api/v1/leads` and `GET /api/v1/leads/due` gain `next_meeting_at`.
- The dashboard shows **Next meeting** on lead rows and the meetings list in the lead's history panel. Exact layout
  follows the wireframes' structure and is settled in the frontend ticket.

When these shapes land, `web/src/lib/api/types.ts` and `web/src/mocks/` change in the same PR, as for every contract
change.

## Logging and test data

Log lines carry counts, status codes and Google reasons only: never titles, descriptions, attendee addresses or
meeting links. Fixtures, the mock server and tests use synthetic events with `example.test`
addresses only.

## Open decisions

| Decision | Proposed default |
|---|---|
| `GOOGLE_INTERNAL_DOMAINS` value | SolTech's Workspace domain(s); set per environment |
| Does a meeting count toward `last_contact_at` or the Due today rule? | No in v1: meetings show as `next_meeting_at` / `last_meeting_at` only, so the existing due semantics do not change |
| Review UI for unresolved calendar events | Unknown invitees surface as inquiries; other `needs_review` events wait for a later review-queue ticket |
| Full-sync window | 90 days back, if the API allows a bounded full sync (see Incremental sync) |
