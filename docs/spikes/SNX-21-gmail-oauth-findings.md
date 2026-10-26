# SNX-21 Gmail OAuth spike findings

Decision date: **October 26, 2026 (Asia/Manila)**. Decision: **GO for SNX-32 development against the team-controlled synthetic mailbox**. Status: research evidence recorded; peer review and integration remain required before Done.

This proves real Gmail API access, token refresh, and repeatable thread extraction. It does not establish production client access, PostgreSQL ingestion, or completion of FR-01. The October 20 decision target in the ticket was missed; this records the actual evidence date rather than backdating the result.

## Ownership and access

JM Briz confirmed on October 26 that he controls recovery for both test Gmail accounts and the Google Cloud project, and owns credential/token revocation and reissue. The two accounts act as the SolTech test mailbox and a synthetic clinic correspondent. Account addresses, recovery details, project/client IDs, passwords, authorization URLs, and tokens are deliberately excluded from this report.

| Item | Verified state and evidence |
| --- | --- |
| OAuth client | Downloaded JSON identifies a Desktop app; used successfully through Docker. |
| Gmail API | Operator confirmed enabled; successful API calls corroborate access. |
| Audience | Operator confirmed External / Testing and added the SolTech test mailbox as a test user. |
| Scope | Probe requests only `https://www.googleapis.com/auth/gmail.readonly`; operator configured it in Data Access. A local check of the saved token's scope list confirmed this was the only scope; no token values were printed. |
| Consent and tokens | Browser consent completed; local token file was created with mode `600` and is git-ignored. Forced refresh succeeded on repeated runs. |
| Content | Operator-created synthetic three-message conversation; no client mailbox or real clinic rows were used. Bodies and addresses are not printed or stored as evidence. |
| Secret isolation | `.secrets/` is mounted at runtime only into the probe service; the Docker build context excludes it. |

`gmail.readonly` is the least privilege suitable for this standalone body-reading probe. `gmail.metadata` cannot read bodies; send/modify/delete permissions are unnecessary. Google classifies the chosen scope as restricted. See [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes).

## Reproduction and redacted evidence

Follow the [Docker runbook](../../backend/spikes/README.md). The verified synthetic conversation uses this query:

```bash
docker compose --profile spike run --rm --service-ports gmail-spike \
  --query 'subject:"Question about SolTech EMR"' --verify-refresh
```

Run A was observed from the Docker probe during this session on October 26. Run B was a separate rerun by JM Briz on the same setup; its redacted output was supplied in this session on October 26. Both produced the same output:

```text
refresh_succeeded: true
thread_fingerprint: 0039add9b3bd
message_count: 3
message: id_fingerprint=0039add9b3bd direction=inbound event_at=2026-10-25T02:26:56+00:00 text_present=true
message: id_fingerprint=adb6248c8ddb direction=outbound event_at=2026-10-25T02:27:49+00:00 text_present=true
message: id_fingerprint=c8a71273be6a direction=inbound event_at=2026-10-25T02:28:34+00:00 text_present=true
```

The probe calls `threads.list`, then `threads.get(format="full")` for exactly one match. It decodes nested plain-text MIME bodies in memory to confirm nonempty content. It prints 12-character SHA-256 prefixes of provider IDs, never raw IDs or bodies. Equal fingerprints on both runs support repeatable source identity; they are display evidence, not database keys or a proof of deduplication. The thread and first message share a fingerprint because they share the provider ID value in this sample.

`event_at` is Gmail's `internalDate`, converted from epoch milliseconds to UTC. Direction uses the authorized mailbox's `SENT`/`INBOX` labels; messages with neither are reported as unknown. This limited method is sufficient for this sample, not a general solution for archived mail, aliases, or forwarded messages. SNX-32 must preserve original sender/recipient identifiers and scope source IDs to the connected account under the [data contract](../contracts/phase1-data-api-v1.md). A clinic name in a reply does not create a staff-confirmed clinic link; the [identity contract](../contracts/phase1-identity-v1.md) still applies. See Google's [message resource](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages) and [thread search](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/list).

Two earlier failures were resolved: the example subject returned zero matches until replaced by the actual subject; an unrelated localhost callback caused a state mismatch until the probe rejected unmatched callbacks and continued waiting. The callback filter was checked inside Docker using fake requests: an unrelated request returned HTTP 400 and a matching synthetic callback returned HTTP 200. This preserves state validation; it does not disable the OAuth library's validation.

## Consent lifetime, verification, and Workspace policy

- External / Testing is appropriate for this controlled development spike. Google permits up to 100 listed test users and shows an unverified-app warning. For this Gmail scope, authorization and its refresh token expire after seven days from consent; this is not the ordinary access-token lifetime. Plan to reauthorize for later demos. [Audience rules](https://support.google.com/cloud/answer/15549945?hl=en)
- Google's development/testing exception permits this test without completing public-app verification. It does not prove eligibility for a production exception. Before client deployment, determine whether an organization-owned Internal app is appropriate or external verification is needed. A production app using restricted data through a server may also require a security assessment unless an exception applies. [Verification and exceptions](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)
- Internal apps require a Cloud project associated with the Workspace/Cloud Identity organization; a consumer Gmail test account alone does not establish that arrangement. Workspace administrators can restrict Gmail OAuth access, and `domainPolicy` failures require administrator action. The client's actual policy and approval path were not tested by this spike. [Audience rules](https://support.google.com/cloud/answer/15549945?hl=en), [Gmail errors](https://developers.google.com/workspace/gmail/api/guides/handle-errors)

## Quota and backoff findings

The successful runs did not encounter quota errors. No load test or deliberate quota exhaustion was performed. The probe uses two Gmail calls per successful run and has no explicit retry policy; a transient API error ends the run. Token exchange is a separate OAuth request. Live throttling, automatic backoff, and recovery are **not demonstrated** by this evidence.

Google's current documentation describes simultaneous project and per-user-per-project minute limits and a quota change effective May 1, 2026. Under the documented new schedule, `threads.list` costs 10 units and `threads.get(format="full")` costs 120, totaling 130 Gmail quota units for this probe's successful list/get pair. The actual project's assigned tier/overrides were not inspected; inspect Cloud Console before choosing SNX-32 polling frequency. [Usage limits](https://developers.google.com/workspace/gmail/api/reference/quota)

SNX-32 should retry rate-limit reasons in HTTP 403, HTTP 429, and transient 5xx responses with bounded exponential backoff and jitter, respecting server retry timing where supplied. Proposed starting policy: five retries, delays growing from one second to a 32-second cap plus jitter, then a visible failed run. Policy/configuration errors such as `domainPolicy`, a bad query, or revoked credentials need operator action rather than an endless retry loop. This is an implementation recommendation, not behavior implemented in the probe. Test it with synthetic fault injection rather than intentionally overwhelming Gmail. [Google's error and retry guidance](https://developers.google.com/workspace/gmail/api/guides/handle-errors)

## Recovery, rotation, and fallback

JM Briz owns the following operator actions; recovery secrets remain in private account settings, not documentation:

1. For expired/revoked consent (`invalid_grant`), stop the probe, revoke the test app's connection in the Google Account if needed, remove only the local ignored `gmail-token.json`, and rerun Docker to consent as the SolTech test mailbox. Deleting a local file alone does not revoke Google's grant.
2. For an exposed/replaced OAuth client, revoke affected grants and replace/reset the Desktop client through Cloud Console. Replace the ignored client JSON, discard the affected local token, reauthorize, and verify a read plus forced refresh. Do not commit or send credentials to teammates through Jira/PRs. [Google OAuth token revocation](https://developers.google.com/identity/protocols/oauth2/web-server#tokenrevoke)
3. For a mailbox/project lockout, use the private recovery controls for the affected account. A newly designated operator must receive explicit ownership/access and run the same proof before relying on the replacement setup.
4. For provider outage, policy denial, expired consent, or quota exhaustion, record the failed live attempt and stop claiming live Gmail behavior. Use the existing [synthetic contract fixtures](../contracts/fixtures/phase1-api-examples-v1.json) for downstream development and a clearly labeled recorded/demo fallback. Fixtures do not satisfy FR-01 or turn a failed future access test into GO.

## Acceptance and handoff

| Criterion | Outcome |
| --- | --- |
| Real Gmail read and successful refresh | Passed: two matching runs above. |
| Inbound/outbound text, timestamps, stable IDs | Passed for the three-message synthetic sample. |
| Ownership, access steps, limits, fallback, decision | Recorded here and in the runbook; production Workspace access remains unverified. |
| Quota/backoff investigation | Provider policy reviewed; probe fail-fast behavior documented; live throttling/backoff implementation is not claimed. |
| Original October 20 target | Missed; verified GO evidence is dated October 26. |
| Peer review and integration | Pending another developer's review and merge into protected `main`. Do not mark Done until this gate is met. |

SNX-32 can use this test setup to implement account-scoped IDs, MIME handling, incremental checkpoints, replay protection, bounded retries, and unknown-clinic inquiries. SNX-26 owns durable schema work; SNX-33 owns orchestration. None of those implementations is delivered by this spike.
