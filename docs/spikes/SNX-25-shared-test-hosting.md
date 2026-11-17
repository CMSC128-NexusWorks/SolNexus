# SNX-25 shared test hosting research

Decision date: pending. Decision: **pending** (recommendation below). Status: research only; nothing deployed.

This compares hosts for one shared Phase 1 environment (API, dashboard, Airflow, PostgreSQL) loaded with synthetic data only. It records what any host must provide, the current provider terms, a recommendation, and the steps a person must take to reach GO. It does not show that the team can deploy or reach a shared environment: no account was created, no VM was started and nothing was measured. JP Salomeo (Scrum Master) and JM Briz (Product Owner) make the GO/NO-GO call. SNX-34 does the deployment itself.

All provider facts were read from the linked official pages on **2026-11-17** unless marked unverified. Prices are USD and change; recheck them before creating an account.

## What any host must provide

These come from `compose.yaml`, `.env.example`, the Dockerfiles, [authentication](../authentication.md) and the [SNX-21 findings](SNX-21-gmail-oauth-findings.md).

| Need | Why |
| --- | --- |
| About 8 GB RAM; 4 GB is the floor | Airflow's [Docker Compose guide for 2.10.5](https://airflow.apache.org/docs/apache-airflow/2.10.5/howto/docker-compose/index.html) says "You should allocate at least 4GB memory for the Docker Engine (ideally 8GB)". Our host also runs Postgres, the API, the dashboard and a proxy. The same page says the compose file "does not provide any security guarantees required for production system". |
| One site over HTTPS for dashboard and API | The session cookie is `HttpOnly; Secure; SameSite=Lax; Path=/api`. Dashboard and API must be on the same site; different sites would need `SameSite=None` plus a CSRF token, which is not built. The simplest layout is one origin: `/` serves the built dashboard and `/api` (plus `/health`) goes to FastAPI. `CORS_ORIGINS` must list that origin. |
| Only 80/443 public | `compose.yaml` publishes Postgres, API 8000, web 5173 and Airflow 8080 with no host address. Docker then [publishes to all host addresses and calls this "insecure by default"](https://docs.docker.com/engine/network/port-publishing/), and published ports [skip ufw rules](https://docs.docker.com/engine/network/packet-filtering-firewalls/). SNX-34 must bind internal ports to `127.0.0.1` (or drop them) and rely on the cloud firewall, not only ufw. |
| Airflow UI private | Reach it over an SSH tunnel or a private network, never the open internet. Replace the `admin`/`admin` login and the sample Fernet and webserver keys from `.env.example` with fresh values on the host. |
| Secrets on the host only | `.env` and `.secrets/gmail-token.json` are copied to the host over SSH by the account owner. They never go into the repo, Jira, PR text or chat. |
| Synthetic data only | Real client rows stay in the git-ignored `leads-data/` folder on developer machines and are never uploaded to the shared host. Staff accounts on the host use `example.test` emails. |
| Weekly Gmail reauthorization | The External/Testing consent and refresh token expire seven days after consent (SNX-21). An always-on host will see Gmail sync fail weekly until the owner reauthorizes locally and copies the new token file over SSH. Reauthorize shortly before any demo. |
| Up for Sprint 4 | SNX-46 and SNX-47 (November 27 to December 4) need deployment and demo evidence, so the host should stay up at least until December 4 without someone's PC being on. |
| arm64 is acceptable | Docker Hub lists `arm64` builds for `apache/airflow:2.10.5-python3.12`, `postgres:16-alpine`, `node:22-alpine`, `python:3.12-slim` and `caddy:2`. The dbt pip install on arm64 is unverified. |

## Options compared

| Option | Cost to the team | RAM | Always on | HTTPS route | Account needs | Phase 2 S3 fit |
| --- | --- | --- | --- | --- | --- | --- |
| AWS EC2, Free plan credits | $0 while credits last; about $87/month of credit on `m7i-flex.large` | 8 GiB (`m7i-flex.large`) or 4 GiB (`c7i-flex.large`) | Yes, until credits or 6 months run out | Caddy + DNS name, or Tailscale serve | Payment method not required for most new customers | Same provider |
| AWS Lightsail 4 GB | $24/month | 4 GB | Yes | Caddy + DNS name | Free-plan availability unverified | Same provider |
| Oracle Always Free A1 | $0 | Up to 12 GB | Yes, but idle instances may be reclaimed | Caddy + DNS name, or Tailscale serve | Credit card for most users | Different provider |
| Azure for Students | $0 within $100 credit for 12 months | Depends on VM size; not priced here | Yes, until credit runs out | Caddy + DNS name | No card; full-time university student | Different provider |
| Heroku (Student Pack) | $13/month credit for 24 months | Not suited | Yes | Platform domain | Card required | Different provider |
| Team PC + Tailscale | $0 | The PC's | Only while the PC is on | `tailscale serve` on a `ts.net` name | Up to 6 users free | None |

### AWS EC2 and Lightsail

- New accounts since July 15, 2025 choose a Free or Paid plan. Both get **$100 in credits plus up to $100 more** from activities. The Free plan ends "after six months or when your credits are fully used", and then the account closes, with content kept 90 days ([AWS plans](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html), [AWS Free Tier](https://aws.amazon.com/free/)). The Free plan cannot incur charges.
- "A payment method isn't required to sign up for most new customers", though AWS may ask for one to verify identity ([Free Tier FAQs](https://aws.amazon.com/free/free-tier-faqs/)).
- Free-tier-eligible EC2 types for new accounts: `t3.micro`, `t3.small`, `t4g.micro`, `t4g.small`, `c7i-flex.large`, `m7i-flex.large` ([EC2 free tier](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html)). The micro and small types have 2 GiB or less, too small for this stack. Whether the Free plan lets you launch `t3.medium` or `t4g.medium` is **unverified**.
- On-demand Linux prices in Asia Pacific (Singapore), from the price data behind the [EC2 on-demand pricing page](https://aws.amazon.com/ec2/pricing/on-demand/) (published 2026-11-14). Monthly is hourly × 730.

  | Type | vCPU / RAM | Hourly | About monthly |
  | --- | --- | --- | --- |
  | `t4g.medium` | 2 / 4 GiB | $0.0424 | $30.95 |
  | `t3.medium` | 2 / 4 GiB | $0.0528 | $38.54 |
  | `c7i-flex.large` (free-tier eligible) | 2 / 4 GiB | $0.09778 | $71.38 |
  | `m7i-flex.large` (free-tier eligible) | 2 / 8 GiB | $0.1197 | $87.38 |

- A public IPv4 address costs $0.005/hour (about $3.65/month), in use or idle ([VPC pricing](https://aws.amazon.com/vpc/pricing/)). EBS disk is extra and not priced here. Whether credits cover the IPv4 charge is **unverified**.
- From November 18 to December 4 (408 hours), `m7i-flex.large` plus IPv4 comes to about $51 of credit, within the $100 sign-up credit.
- Lightsail Linux bundles include a public IPv4: 2 GB at $12, **4 GB at $24**, 8 GB at $44 per month ([Lightsail pricing](https://aws.amazon.com/lightsail/pricing/)). The page says Lightsail can be started for free under the Free Tier but names no plan or period; whether Lightsail is on the Free plan, and which bundles, is **unverified**.

### Oracle Cloud Always Free (Ampere A1)

- Always Free A1 is "equivalent to 2 OCPUs and 12 GB of memory", with 200 GB block storage, created only in the home region ([Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)).
- Oracle may reclaim an Always Free instance as idle if, over 7 days, 95th-percentile CPU, network and (for A1) memory are all under 20% (same page). Whether our stack stays above the memory line on a 12 GB VM is untested.
- "Out of host capacity" means a temporary shortage of Always Free shapes in the home region; Oracle says to try another availability domain or wait (same page).
- "Most users need a mobile phone number and a credit card to create an account"; the card is not charged unless you upgrade. Always Free resources continue after the $300/30-day trial ([Free Tier overview](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm)). The marketing pages at oracle.com returned HTTP 403 to automated fetches.

### GitHub Student Developer Pack

- The [pack page](https://education.github.com/pack) currently lists Microsoft Azure ($100 credit, no card, 18+) and Heroku ($13/month for 24 months). It does **not** list DigitalOcean, and [DigitalOcean's student page](https://www.digitalocean.com/github-students) no longer describes a pack offer.
- [Azure for Students](https://azure.microsoft.com/en-us/free/students): $100 credit within 12 months, no card, "full-time university students", sign-up with a school email, 750 hours each of B1s, B2pts v2 and B2ats v2 VMs for 12 months. The RAM of those free sizes was not checked; whether $100 covers an 8 GB VM to December 4 is unverified.
- [Heroku for GitHub Students](https://www.heroku.com/github-students): $13/month for 24 months, 18+, card required. Running Airflow's scheduler, webserver and our compose stack on dynos is a re-architecture, not a fit for this ticket.
- Pack eligibility: enrolled in a degree- or diploma-granting program, documents proving current status, a personal GitHub account, age 13+ ([GitHub Education](https://docs.github.com/en/education/about-github-education/github-education-for-students/apply-to-github-education-as-a-student)).

### Team PC + Tailscale

- The Personal plan is free for up to 6 users with unlimited user devices, and is "only suitable for non-commercial use" ([Tailscale pricing](https://tailscale.com/pricing)). Five developers fit; adding SolTech staff would exceed 6. Whether a client-facing student project counts as non-commercial is a judgment for the decision makers.
- `tailscale serve` shares a local service with the tailnet only and requires HTTPS certificates to be enabled; `--set-path` maps a path, and `--bg` keeps it running after restarts ([serve](https://tailscale.com/kb/1312/serve), [CLI](https://tailscale.com/kb/1242/tailscale-serve)). That gives one `ts.net` origin with `/` and `/api`, which satisfies the cookie rule.
- Certificates come from Let's Encrypt with MagicDNS on, and machine names appear in public Certificate Transparency logs ([HTTPS](https://tailscale.com/kb/1153/enabling-https)). Funnel would make it public on ports 443, 8443 or 10000 ([Funnel](https://tailscale.com/kb/1223/funnel)).
- The environment is down whenever the PC sleeps, reboots or leaves the network, so it cannot carry Sprint 4 alone.

### Split PaaS hosting is ruled out

`vercel.app` and `onrender.com` are both on the [Public Suffix List](https://publicsuffix.org/list/public_suffix_list.dat) (version 2026-11-15). Each project subdomain is therefore its own site, so a dashboard on `*.vercel.app` and an API on `*.onrender.com` are cross-site and the `SameSite=Lax` cookie will not work. A shared custom domain would avoid this, but it still splits Airflow and Postgres onto other services.

### HTTPS on a VM: Caddy and the DNS name

- Caddy gets and renews certificates by itself when the domain's A/AAAA records point at the server, ports 80 and 443 are open externally, its data directory is writable and persistent, and the domain is in the config. It redirects HTTP to HTTPS ([Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https)).
- Let's Encrypt allows 50 new certificates per registered domain per 7 days, counted across all accounts, using the Public Suffix List to find the registered domain ([rate limits](https://letsencrypt.org/docs/rate-limits/)).
- `sslip.io` and `nip.io` are not on the Public Suffix List, so every user of those services shares one 50-per-week budget. Avoid them. `duckdns.org` is on the list, so each DuckDNS subdomain gets its own budget; DuckDNS's reliability and terms were not checked. A team-owned domain is the most predictable; its price was not checked.
- Tailscale serve on the VM is a no-DNS alternative: HTTPS on a `ts.net` name with no public ports, limited to tailnet members.

## Recommendation

**Primary: one AWS EC2 `m7i-flex.large` (8 GiB) in Asia Pacific (Singapore) on a new account's Free plan, running the compose stack behind Caddy on one HTTPS origin.** Reasons:

- $0 to the team and no bill risk: the Free plan cannot charge, and a card is not needed for most new sign-ups.
- 8 GiB meets Airflow's "ideally 8GB"; `c7i-flex.large` (4 GiB) is the cheaper step down if credits get tight.
- About $51 of the $100 credit covers November 18 to December 4.
- Same provider as the proposal's "AWS (EC2/RDS) or equivalent" and as Phase 2 S3, though S3 stays a separate SNX-39 gate.
- Always on for Sprint 4 without anyone's PC.

Known costs of this choice: the account closes when credits run out or after six months, so this is a semester test host, not a long-lived one. Someone must watch the credit balance weekly. A DNS name is still needed for Caddy; if none is ready, start with Tailscale serve on the VM and add Caddy later.

**Fallback: Team PC + Tailscale serve.** It needs no cloud account or card and can be running today for Phase 1 integration checks among the five developers. It does not meet the always-on need, so if it becomes the Sprint 4 host, the demo must run from that PC. If AWS sign-up fails and someone can supply a card, Oracle Always Free A1 is the always-on alternative, with capacity and idle-reclaim risk.

## Constraints to record

- **Credentials ownership.** One named team member owns the cloud account and its recovery, with MFA on the root login, and creates individual logins for teammates instead of sharing the root password. The owner's name is recorded in Jira; recovery emails, phone numbers, account IDs and keys are not recorded anywhere in the repo or Jira. The Gmail test project and token stay owned by JM Briz as in SNX-21.
- **Secrets.** `.env`, `.secrets/` and SSH private keys live on the host and on the owner's machine only. Generate new Postgres, Airflow admin, Fernet and webserver values for the host. Rotate them if they are ever pasted into chat, Jira or a PR.
- **HTTPS callbacks.** Phase 1 needs no inbound callbacks: Gmail is polled and the OAuth consent runs on a local machine. Phase 2 Facebook and Viber webhooks need a public HTTPS endpoint. Per the acceptance criteria, that hosting is decided after Phase 1 acceptance (SNX-22, SNX-23) and does not gate this environment. A tailnet-only host would not serve those callbacks.
- **Test vs live data.** The shared host holds synthetic data and synthetic staff accounts only. No real client mailbox is connected and no `leads-data/` file is uploaded. A client-facing deployment with real data is a separate decision.
- **Phase 2 gates stay separate.** S3 access (SNX-39) and failure-alert provider (SNX-42) are not tested or decided here.

## What a human must do to reach GO

1. JP Salomeo and JM Briz pick the host (primary, fallback or other) and record the decision date here.
2. Name the account owner. The owner creates the account, turns on MFA, picks the Singapore region and, on AWS, keeps the Free plan.
3. Choose the HTTPS route: a DNS name for Caddy (team domain or a PSL-listed free subdomain), or Tailscale serve.
4. Create the VM (`m7i-flex.large`, Ubuntu LTS or similar, about 30 GB disk). Open only 22 (restricted to the owner's IP or key-only SSH), 80 and 443 in the cloud firewall. With Tailscale serve, open only 22.
5. Install Docker, copy `.env` and `.secrets/` over SSH, and hand off to SNX-34 with these host needs: built dashboard served as static files instead of `npm run dev`, `uvicorn` without `--reload`, a production API image (`INSTALL_DEV` unset), internal ports bound to `127.0.0.1`, a DB readiness check, Caddy routing `/` and `/api` + `/health` on one origin, `CORS_ORIGINS` and `VITE_API_URL` set to that origin, and a runbook.
6. Seed synthetic data and create the two synthetic staff accounts with `python -m app.staff_account`.

Evidence to record for GO (redacted, no secrets):

- The URL, reached by at least two teammates from their own networks.
- `GET /health` returns OK over HTTPS.
- Login sets the session cookie and the dashboard loads leads over HTTPS.
- Airflow UI is not reachable from the internet (port 8080 refused from outside) and is reachable through the tunnel or tailnet with a non-default password.
- Postgres port refused from outside.
- One Gmail sync and one silver refresh succeed on the host.
- The credit balance and the date credits are expected to run out.

## Acceptance

| Criterion | Outcome |
| --- | --- |
| Select a shared environment for API, dashboard, Airflow, database | Recommendation recorded; decision **pending**. |
| Team can deploy and reach a shared synthetic-data environment | **Not met: nothing deployed yet.** Needs the steps above and SNX-34. |
| Credentials, HTTPS callback and deployment constraints recorded without secrets | Recorded above; account owner not yet named. |
| Phase 2 Facebook callback hosting decided after Phase 1, not gating this | Recorded; not decided here. |
| S3 and failure-alert access remain separate Phase 2 gates | Recorded; left to SNX-39 and SNX-42. |
| GO/NO-GO outcome | **Pending** JP Salomeo and JM Briz. |
| Peer review | Pending review and merge into protected `main`. |

## Unverified

- Whether the AWS Free plan allows `t3.medium`/`t4g.medium`, whether Lightsail is on it, and whether credits cover public IPv4.
- EBS and domain prices; RAM of the Azure free VM sizes.
- Oracle's marketing pages (403); facts above come from Oracle's docs instead.
- Whether the dbt install works on arm64, and whether our stack would trip Oracle's idle-reclaim thresholds.
- DuckDNS reliability and terms.
