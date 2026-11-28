# Mock Google datasets

Each `<name>.json` file here seeds the mock Google server with one Gmail mailbox and one Google Calendar, plus a list of
**scripted changes** that tests replay to exercise incremental sync. The mock loads the file named by `MOCK_DATASET`
(default `synthetic_soltech`). It refuses to start if the file is invalid or a scripted change cannot apply.

**Everything is synthetic.** People, clinics, addresses and links are invented and use `example.test` domains only, as
the repo's data rules require ([AGENTS.md](../../../../AGENTS.md)). A unit test fails if any other email domain appears.
Product details (SolTech's YAKAP EMR, plans, demo, support channels) are paraphrased from soltech.ph as of November 2026,
so the conversations read like real SolTech sales mail.

## `synthetic_soltech.json` at a glance

| | Count | Notes |
|---|---|---|
| Messages | 10 seeded, +1 scripted | Mailbox `sales@soltech.example.test`; history IDs start after `104000` |
| Calendar events | 8 seeded (13 stored), +1 scripted | Calendar owner `sales@soltech.example.test`, calendar time zone `Asia/Manila` |
| Scripted changes | 6 | New mail, a deletion, a reschedule, two cancellations, a new booking |

### Who is in it

| Clinic (invented) | Location | Story | Tests |
|---|---|---|---|
| Reyes Family Clinic | Imus, Cavite | Asks about pricing, eKonsulta import and staff accounts; SolTech replies; she books a Calendly demo, which is later rescheduled | A 3-message thread (inbound, outbound, inbound) threaded with `In-Reply-To`; a reschedule creating a new event version |
| Northpoint Medical Clinic | 3 branches, Cebu | Asks about multi-clinic reporting and Enterprise pricing; gets an all-day onboarding visit and a weekly go-live series | A first contact with no reply yet; an all-day event; a weekly series with one occurrence cancelled |
| Peña Pediatrics | Quezon City | Taglish inquiry about offline mode and training; books a demo, then cancels it | Non-ASCII name and subject (RFC 2047 encoding); a cancelled event |
| Villanueva Medical Clinic | Iloilo City, managed from California | The owner's son writes and books in Pacific time; a weekly onboarding sync runs over the US daylight-saving change | An email `Date` with a `-08:00` offset; an event in another time zone; a series whose UTC offset changes |
| Sunrise Family Health Center | Davao City | Scripted: new lead from Facebook, then books a demo | Incremental sync of new mail and a new booking from the same person (one shared inquiry) |

### Messages

| ID | Thread | Labels | From → to | What it is | Should the master ingest it? |
|---|---|---|---|---|---|
| `msg-001` | `thr-001` | INBOX | Reyes → SolTech | Pricing / migration inquiry | Yes, inbound first contact |
| `msg-002` | `thr-001` | SENT | SolTech → Reyes | Reply: Basic plan, eKonsulta import, demo link | Yes, outbound |
| `msg-003` | `thr-002` | INBOX, UNREAD | Northpoint → SolTech | Multi-branch and pricing question | Yes, inbound first contact |
| `msg-004` | `thr-003` | INBOX, CATEGORY_PROMOTIONS | Newsletter → SolTech | Industry newsletter (deleted by a scripted change) | Stored by the Gmail connector today; selection rules may exclude it later |
| `msg-005` | `thr-002` | DRAFT | SolTech → Northpoint | Unsent Enterprise quote | No: drafts are skipped |
| `msg-006` | `thr-004` | SPAM | Fake "accreditation" sender | Phishing spam | No: spam is skipped |
| `msg-007` | `thr-005` | INBOX | SolTech onboarding → SolTech sales | Internal demo prep | Stored today; internal mail is a selection question |
| `msg-008` | `thr-006` | INBOX | Peña → SolTech | Taglish inquiry, non-ASCII name | Yes, inbound first contact |
| `msg-009` | `thr-001` | INBOX | Reyes → SolTech | "I booked the demo" | Yes, same identity as `msg-001` |
| `msg-010` | `thr-007` | INBOX | Villanueva (California) → SolTech | Inquiry sent with a `-08:00` time | Yes, inbound first contact |

Messages are rendered once to RFC 822 bytes, deterministically (same file, same bytes), because the master treats a
replayed message whose bytes differ as a discrepancy.

### Calendar events

All bookings follow Calendly's real output: the title "SolTech Free 30-Minute Demo between SolTech Sales and <invitee>",
a Meet link, the invitee's form answers, cancel/reschedule links and the marker "Powered by Calendly.com".

| ID | When | Kind | Should the master ingest it? |
|---|---|---|---|
| `evt-calendly-reyes-demo` | 2026-12-02 10:00 Manila (rescheduled to 12-04 15:00) | Calendly demo | Yes: external attendee |
| `evt-calendly-villanueva-demo` | 2026-12-03 17:00 Los Angeles (= 12-04 09:00 Manila) | Calendly demo, other time zone | Yes |
| `evt-calendly-pena-demo` | 2026-12-03 14:00 Manila (cancelled) | Calendly demo | Yes, including the cancellation |
| `evt-northpoint-onboarding-day` | 2026-12-07, all day | Onboarding visit | Yes |
| `evt-northpoint-golive-weekly` | Weekly from 2026-12-02 14:00 Manila, 4 times (12-16 cancelled) | Recurring series | Yes, as 4 occurrences |
| `evt-villanueva-weekly-dst` | Weekly from 2027-03-04 17:00 Los Angeles, 3 times | Series across daylight saving | Yes, as 3 occurrences |
| `evt-internal-standup` | 2026-12-01 09:00 Manila | Internal meeting | **No**: no external attendee |
| `evt-personal-block` | 2026-12-01 13:00 Manila | Personal work block | **No**: no attendees |

The ingest column follows the [calendar contract](../../../../docs/contracts/google-calendar-v1.md): only events with at
least one attendee outside SolTech's domains.

### Scripted changes, in order

| # | Change | What it exercises |
|---|---|---|
| 0 | `add_message` `msg-011` from Sunrise | Gmail incremental sync picks up new mail |
| 1 | `delete_message` `msg-004` | Gmail history reports a deletion |
| 2 | `reschedule_event` Reyes demo to 12-04 15:00 | A new event version: new `etag`, `sequence` + 1, same ID |
| 3 | `cancel_event` Peña demo | A cancellation reaches incremental sync as `status: cancelled` |
| 4 | `cancel_event` `evt-northpoint-golive-weekly_20261216T060000Z` | Cancelling one occurrence leaves the rest of the series |
| 5 | `add_event` Sunrise demo | A booking from the same person as new mail (one inquiry, not two) |

## How the mock turns the file into Google data

- **Recurring events** are stored as expanded occurrences, never as the series itself, because the master reads with
  `singleEvents=true`. Occurrence IDs follow Google's format: `<series id>_<start in UTC>`, e.g.
  `evt-northpoint-golive-weekly_20261209T060000Z` (`_<YYYYMMDD>` for all-day series).
- **Times:** an event time is either `{"date": "2026-12-07"}` (all day) or a local `date_time` with no offset plus an
  IANA `time_zone`. Series repeat in local wall-clock time, so a 17:00 Los Angeles meeting stays at 17:00 after daylight
  saving starts and its UTC offset changes from `-08:00` to `-07:00`. Message `sent_at` values must carry an offset.
- **Versions:** every event write gets the next calendar change number, a new `etag` and `updated` time. Seeded
  versions use `seeded_at` as their time, so seeding is deterministic.

## Adding or editing a dataset

1. Copy `synthetic_soltech.json` to `<new_name>.json` (lowercase letters, digits and `_` only) and edit it.
2. Keep every address on an `example.test` domain and every person and clinic invented.
3. Start the mock with `MOCK_DATASET=<new_name>`. If anything is wrong, it lists every problem with the field or the
   scripted change's position, and does not start.
4. Run the mock's tests: `docker compose --profile test run --rm google-workspace-mock-tests`.

The schema lives in [`mock_dataset.py`](../mock_dataset.py): unknown fields are errors, and the only supported
recurrence rules are `RRULE:FREQ=DAILY;COUNT=n` and `RRULE:FREQ=WEEKLY;COUNT=n`.
