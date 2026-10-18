# Phase 1 clinic and message identity contract — v1

Status: agreed entity-resolution decision for SNX-20; remaining SNX-20 data and API contracts are pending.

This contract covers Gmail and Facebook Page messages in Phase 1. The same identity boundary applies to supported Viber messages in Phase 2. A clinic created through initial spreadsheet migration or by staff has its own internal `clinic_id`. Message ingestion never creates or merges clinics.

## Source identity and evidence

The source identity key is `(source_channel, source_account_id, external_participant_id)`. All three parts must come from the connector's source data and be retained with the raw message. `source_account_id` scopes an identity to the connected mailbox or Page. `external_participant_id` identifies the clinic-side participant: the sender of an inbound message or the recipient of an outbound message. Keep the original sender and recipient identifiers separately. If a message has no unique external participant, it needs review. A source identifier identifies an account or address, not the clinic it represents.

Clinic name, sender name, and location can suggest candidate clinics. Location is optional and cannot identify a clinic by itself. Similar names, even with a plausible location, do not authorize automatic linking, clinic creation, or clinic merging. Contact details in the imported workbook are candidate evidence only.

SolTech staff must first confirm that an exact source identity key belongs to one existing `clinic_id`. Record the confirming staff user and confirmation time with that mapping. A confirmation for one channel or source account does not verify another channel or source account. A mapping's history must remain traceable when staff correct it.

## Resolution outcome

For each ingested message, preserve the original source identifiers and unmodified raw payload before resolving its clinic. Retain source event time and ingestion time separately when available. The message has one of these outcomes:

| Outcome | Rule | Stored clinic link | Staff review |
|---|---|---|---|
| `linked` | The complete source identity key has exactly one active staff-confirmed clinic mapping and the message contains no detected evidence conflicting with that clinic. | Confirmed `clinic_id` | No |
| `needs_review` | No confirmed mapping, incomplete source identity, more than one active confirmed mapping, or detected conflicting evidence. | `null` | Yes |

First-contact messages remain unlinked until staff confirms the source identity's clinic mapping, even when clinic name, sender name, and location appear to match. An absent location does not block a link through an otherwise unambiguous confirmed mapping. If evidence conflicts with a confirmed mapping, the message remains unlinked for staff review; the mapping does not override the conflict. No match, multiple matches, and conflicting evidence all require review.

For review reporting, use `no_match` when no clinic candidate is found, `multiple_candidates` when the evidence suggests several clinics and no confirmed source mapping resolves them, `unconfirmed_source_identity` when a plausible clinic exists but the source identity has not been staff-confirmed, `incomplete_source_identity` when the source key is missing a part, `multiple_confirmed_mappings` when one key has competing active confirmations, and `conflicting_evidence` when message evidence contradicts the confirmed clinic. Candidate lookup cannot authorize a link on its own. A confirmed unique mapping may still link a message that mentions a clinic name shared by several records, provided there is no conflicting evidence.

Review must expose the raw message, source identifiers, candidate clinic information when available, and the reason it was not linked. Staff may confirm or correct a source identity mapping and resolve a message to an existing clinic. Review does not create or merge clinics automatically. The contract does not yet decide whether resolving one message retrospectively relinks other messages from the same sender.

## Minimum fields at this boundary

| Field | Purpose |
|---|---|
| `source_channel`, `source_account_id`, `external_participant_id` | Exact clinic-side source identity key; preserve original values. |
| `direction`, `source_sender_id`, `source_recipient_ids` | Preserve who sent and received the message; `direction` is inbound or outbound. |
| `source_message_id`, `source_thread_id` | Source message and conversation lineage; `source_thread_id` may be null if the channel provides none. |
| `source_event_at`, `ingested_at` | Keep source and ingestion times distinct; source time may be null if unavailable. |
| `raw_payload` | Unmodified source record; retain even when unresolved. |
| `clinic_id` | Internal clinic ID only after a permitted link; otherwise null. |
| `resolution_status`, `review_reason` | `linked` or `needs_review`, plus the reason for review. |
| `confirmed_by`, `confirmed_at` | Staff user and time on the source-to-clinic mapping, not inferred from message text. |

The connector-specific format of source IDs, candidate matching and conflict detection, storage tables, review UI, and retrospective relinking remain implementation decisions for dependent tickets. Those choices must preserve the rules above. The synthetic cases in [identity-resolution-v1.json](fixtures/identity-resolution-v1.json) illustrate the required outcomes without client data.
