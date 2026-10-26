# SNX-21 Gmail OAuth probe

This one-off Docker service proves that the team-controlled synthetic mailbox can grant read-only Gmail access, return a conversation, and refresh its OAuth token. It does not ingest into PostgreSQL; that belongs to SNX-32.

1. Put the downloaded Desktop OAuth client JSON at `.secrets/gmail-oauth-client.json`. Keep `.secrets/` private and git-ignored. The test mailbox must be an OAuth test user and contain only synthetic conversations.
2. Build the probe image: `docker compose --profile spike build gmail-spike`.
3. Run a query matching exactly one test thread, for example:

   ```bash
   docker compose --profile spike run --rm --service-ports gmail-spike \
     --query 'subject:"SNX-21 synthetic inquiry"' --verify-refresh
   ```

The command prints an authorization URL. Open it in a browser on the same computer running Docker, select the test mailbox, and grant the requested read-only access. The callback uses `localhost:8765`; Compose publishes it only on the host's loopback interface. OAuth tokens are saved as `.secrets/gmail-token.json` with owner-only permissions. On Linux, set `SNX_LOCAL_UID` and `SNX_LOCAL_GID` if your user IDs differ from 1000 so the container can write that file.

The output reports only a hashed thread/message fingerprint, count, direction, UTC event time, and whether plain text is present. Rerun the same command to confirm stable fingerprints. `--verify-refresh` forces a token exchange on each run. Never paste the authorization URL, tokens, or raw mailbox content into Jira or Git.
