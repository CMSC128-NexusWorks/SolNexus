# SNX-21 Gmail OAuth probe

This one-off Docker service proves that the team-controlled synthetic mailbox can grant read-only Gmail access, return a conversation, and refresh its OAuth token. It does not ingest into PostgreSQL; that belongs to SNX-32.

The [October 26 findings and GO evidence](../../docs/spikes/SNX-21-gmail-oauth-findings.md) record repeated real API results, access ownership, OAuth limits, and the SNX-32 handoff. JM Briz owns recovery and credential/token rotation for this test setup.

## Set up the test

In the Google Cloud project containing the Desktop OAuth client, enable Gmail API. In Google Auth Platform, keep Audience set to External / Testing, add the SolTech test mailbox as a test user, and add `https://www.googleapis.com/auth/gmail.readonly` under Data Access. Use two controlled accounts to create a synthetic inbound/outbound/reply thread, then choose the thread's actual subject for the query below. Only the account granting API access needs to be a test user.

1. Put the downloaded Desktop OAuth client JSON at `.secrets/gmail-oauth-client.json`. Keep `.secrets/` private and git-ignored. The test mailbox must be an OAuth test user and contain only synthetic conversations.
2. Build the probe image: `docker compose --profile spike build gmail-spike`.
3. Run a query matching exactly one test thread. This is the subject used for the verified spike:

   ```bash
   docker compose --profile spike run --rm --service-ports gmail-spike \
     --query 'subject:"Question about SolTech EMR"' --verify-refresh
   ```

The command prints an authorization URL. Open it in a browser on the same computer running Docker, select the test mailbox, and grant the requested read-only access. The callback uses `localhost:8765`; Compose publishes it only on the host's loopback interface. OAuth tokens are saved as `.secrets/gmail-token.json` with owner-only permissions. On Linux, set `SNX_LOCAL_UID` and `SNX_LOCAL_GID` if your user IDs differ from 1000 so the container can write that file.

The output reports only a hashed thread/message fingerprint, count, direction, UTC event time, and whether plain text is present. Rerun the same command to confirm stable fingerprints. `--verify-refresh` forces a token exchange on each run. Never paste the authorization URL, tokens, or raw mailbox content into Jira or Git.

External / Testing authorizations for this Gmail scope expire after seven days, including the refresh token. See [Google's audience rules](https://support.google.com/cloud/answer/15549945?hl=en). The findings document distinguishes this test setup from production verification and Workspace administrator approval.

## Expected result and troubleshooting

Success requires `refresh_succeeded: true`, three messages in the synthetic sample, inbound/outbound/inbound directions, and `text_present=true` for each. Repeating the query should preserve thread/message fingerprints and source timestamps unless you change the conversation. A successful repeat read does not prove database deduplication.

| Symptom | Action |
| --- | --- |
| `found 0 or more` | This means zero matching threads. Replace the example with your actual subject and verify which test mailbox granted consent. |
| More than one matching thread | Narrow the Gmail query; the probe intentionally refuses to choose an arbitrary conversation. |
| Consent cannot reach `localhost:8765` | Keep the container running, include `--service-ports`, use a browser on the Docker host, and ensure port 8765 is free. |
| Wrong/missing OAuth state | Use the fresh URL from the current run. Unrelated callbacks are rejected without ending the wait; consent times out after five minutes. |
| `invalid_grant` or expired/revoked token | Follow the recovery procedure in the findings: revoke the grant when appropriate, remove only the ignored token file, and reauthorize. Do not replace the client JSON for an ordinary token expiry. |
| Permission denied on the mounted files | Set `SNX_LOCAL_UID`/`SNX_LOCAL_GID` in `.env` to your Linux user IDs; preserve owner-only credential/token permissions. |
| Docker Compose build panics in its Bake integration | Use `COMPOSE_BAKE=false docker compose --profile spike build gmail-spike` as a local workaround for the Compose version used during this spike. |
| HTTP 403/429 or transient 5xx | The probe has no automatic backoff. Record the failure, check policy/quota guidance, and wait before retrying; see the findings for the proposed SNX-32 retry policy. |

## Local verification without Gmail access

```bash
docker compose --profile spike config --quiet
docker compose --profile spike build gmail-spike
docker compose --profile spike run --rm --no-deps gmail-spike --help
```

The `--help` command exits before loading credentials or making Gmail calls. Rebuild the image after changing the probe or its `requirements.txt`; this service installs its dependencies in Docker, not the host Python environment.
