-- Synthetic development data for the Phase 1 schema. All names, emails and numbers are invented.
-- Run after `alembic upgrade head` (see docs/database.md). Safe to rerun: fixed IDs and
-- ON CONFLICT DO NOTHING mean a second run inserts nothing, which matters because bronze and the
-- audit tables cannot be cleaned up with DELETE.
--
-- Scenarios covered:
--   Harborview  manual clinic; its address was first mapped to the wrong clinic, revoked, then remapped
--   Meadow      clinic created by confirming an unknown-name inquiry from its question/reply thread
--   Riverside   imported from both workbook sheets with an unresolved contact_number conflict
--   open inquiries: one complete source identity, one with no participant (incomplete identity)
--   same Gmail message ID arriving in a second mailbox, which stays unlinked there

BEGIN;

-- Unusable placeholder hashes: login credentials are set up by SNX-27, never seeded.
INSERT INTO app.staff_users (user_id, email, password_hash) VALUES
    ('00000000-0000-4000-8000-000000000001', 'staff.one@example.test', '$dev-seed$login-disabled'),
    ('00000000-0000-4000-8000-000000000002', 'staff.two@example.test', '$dev-seed$login-disabled')
ON CONFLICT DO NOTHING;

INSERT INTO app.clinics (clinic_id, clinic_name, contact_person, contact_number, email, status_code,
                         next_action_date, next_step, origin, version, created_by) VALUES
    ('10000000-0000-4000-8000-000000000001', 'Harborview Clinic', 'Sam Example', '0917 000 0101',
     'harborview@example.test', 'contacted', '2026-10-20', 'Send proposal', 'manual', 2,
     '00000000-0000-4000-8000-000000000001'),
    ('10000000-0000-4000-8000-000000000002', 'Meadow Clinic', 'Alex Example', NULL,
     'meadow.contact@example.test', 'follow_up_needed', '2026-10-27', 'Book demo', 'inquiry', 1,
     '00000000-0000-4000-8000-000000000001'),
    ('10000000-0000-4000-8000-000000000003', 'Riverside Clinic', 'Jo Example', NULL,
     NULL, 'proposal_sent', NULL, NULL, 'import', 1, NULL)
ON CONFLICT DO NOTHING;

INSERT INTO bronze.raw_messages (raw_message_id, source_channel, source_account_id, source_message_id,
                                 source_thread_id, external_participant_id, direction, source_sender_id,
                                 source_recipient_ids, source_event_at, raw_payload_bytes) VALUES
    ('50000000-0000-4000-8000-000000000001', 'gmail', 'sales@soltech.example.test', 'msg-0001', 'thr-harbor',
     'harborview@example.test', 'inbound', 'harborview@example.test', '["sales@soltech.example.test"]',
     '2026-10-18T10:00:00+08:00', convert_to('{"id":"msg-0001","snippet":"Synthetic inquiry about pricing"}', 'UTF8')),
    ('50000000-0000-4000-8000-000000000002', 'gmail', 'sales@soltech.example.test', 'msg-0002', 'thr-harbor',
     'harborview@example.test', 'outbound', 'sales@soltech.example.test', '["harborview@example.test"]',
     '2026-10-18T14:00:00+08:00', convert_to('{"id":"msg-0002","snippet":"Synthetic pricing reply"}', 'UTF8')),
    ('50000000-0000-4000-8000-000000000003', 'gmail', 'sales@soltech.example.test', 'msg-0003', 'thr-new',
     'new.lead@example.test', 'inbound', 'new.lead@example.test', '["sales@soltech.example.test"]',
     '2026-10-25T09:00:00+08:00', convert_to('{"id":"msg-0003","snippet":"Synthetic first contact"}', 'UTF8')),
    ('50000000-0000-4000-8000-000000000004', 'gmail', 'sales@soltech.example.test', 'msg-0004', 'thr-meadow',
     'meadow.contact@example.test', 'inbound', 'meadow.contact@example.test', '["sales@soltech.example.test"]',
     '2026-10-20T09:00:00+08:00', convert_to('{"id":"msg-0004","snippet":"Synthetic first contact"}', 'UTF8')),
    ('50000000-0000-4000-8000-000000000005', 'gmail', 'sales@soltech.example.test', 'msg-0005', 'thr-meadow',
     'meadow.contact@example.test', 'outbound', 'sales@soltech.example.test', '["meadow.contact@example.test"]',
     '2026-10-20T11:00:00+08:00', convert_to('{"id":"msg-0005","snippet":"Synthetic: which clinic are you with?"}', 'UTF8')),
    ('50000000-0000-4000-8000-000000000006', 'gmail', 'sales@soltech.example.test', 'msg-0006', 'thr-meadow',
     'meadow.contact@example.test', 'inbound', 'meadow.contact@example.test', '["sales@soltech.example.test"]',
     '2026-10-21T08:00:00+08:00', convert_to('{"id":"msg-0006","snippet":"Synthetic: Meadow Clinic"}', 'UTF8')),
    ('50000000-0000-4000-8000-000000000007', 'gmail', 'sales@soltech.example.test', 'msg-0007', NULL,
     NULL, 'inbound', NULL, '["sales@soltech.example.test"]',
     NULL, convert_to('{"id":"msg-0007","snippet":"Synthetic message with no unique sender"}', 'UTF8')),
    ('50000000-0000-4000-8000-000000000008', 'gmail', 'support@soltech.example.test', 'msg-0001', 'thr-support',
     'harborview@example.test', 'inbound', 'harborview@example.test', '["support@soltech.example.test"]',
     '2026-10-22T10:00:00+08:00', convert_to('{"id":"msg-0001","snippet":"Synthetic support question"}', 'UTF8'))
ON CONFLICT DO NOTHING;

-- Harborview's address was first confirmed to Riverside by mistake, revoked, then confirmed correctly.
INSERT INTO app.clinic_source_identities (mapping_id, source_channel, source_account_id, external_participant_id,
                                          clinic_id, confirmed_by, confirmed_at, reason,
                                          revoked_at, revoked_by, revoke_reason) VALUES
    ('80000000-0000-4000-8000-000000000001', 'gmail', 'sales@soltech.example.test', 'harborview@example.test',
     '10000000-0000-4000-8000-000000000003', '00000000-0000-4000-8000-000000000001', '2026-10-18T11:00:00+08:00', NULL,
     '2026-10-19T09:00:00+08:00', '00000000-0000-4000-8000-000000000001', 'Wrong clinic selected'),
    ('80000000-0000-4000-8000-000000000002', 'gmail', 'sales@soltech.example.test', 'harborview@example.test',
     '10000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000001', '2026-10-19T09:05:00+08:00',
     'Confirmed by phone', NULL, NULL, NULL),
    ('80000000-0000-4000-8000-000000000003', 'gmail', 'sales@soltech.example.test', 'meadow.contact@example.test',
     '10000000-0000-4000-8000-000000000002', '00000000-0000-4000-8000-000000000001', '2026-10-21T10:00:00+08:00',
     'Name confirmed from reply', NULL, NULL, NULL)
ON CONFLICT DO NOTHING;

INSERT INTO app.lead_inquiries (inquiry_id, source_channel, source_account_id, external_participant_id,
                                origin_raw_message_id, clinic_name_state, contact_person, state, version,
                                closed_at, confirmed_clinic_id) VALUES
    ('70000000-0000-4000-8000-000000000001', 'gmail', 'sales@soltech.example.test', 'new.lead@example.test',
     '50000000-0000-4000-8000-000000000003', 'unknown', NULL, 'open', 1, NULL, NULL),
    ('70000000-0000-4000-8000-000000000002', 'gmail', 'sales@soltech.example.test', 'meadow.contact@example.test',
     '50000000-0000-4000-8000-000000000004', 'confirmed', 'Alex Example', 'closed', 2,
     '2026-10-21T10:00:00+08:00', '10000000-0000-4000-8000-000000000002'),
    ('70000000-0000-4000-8000-000000000003', 'gmail', 'sales@soltech.example.test', NULL,
     '50000000-0000-4000-8000-000000000007', 'unknown', NULL, 'open', 1, NULL, NULL)
ON CONFLICT DO NOTHING;

INSERT INTO app.message_resolutions (raw_message_id, clinic_id, resolution_status, review_reason) VALUES
    ('50000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000001', 'linked', NULL),
    ('50000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000001', 'linked', NULL),
    ('50000000-0000-4000-8000-000000000003', NULL, 'needs_review', 'unconfirmed_source_identity'),
    ('50000000-0000-4000-8000-000000000004', '10000000-0000-4000-8000-000000000002', 'linked', NULL),
    ('50000000-0000-4000-8000-000000000005', '10000000-0000-4000-8000-000000000002', 'linked', NULL),
    ('50000000-0000-4000-8000-000000000006', '10000000-0000-4000-8000-000000000002', 'linked', NULL),
    ('50000000-0000-4000-8000-000000000007', NULL, 'needs_review', 'incomplete_source_identity'),
    ('50000000-0000-4000-8000-000000000008', NULL, 'needs_review', 'unconfirmed_source_identity')
ON CONFLICT DO NOTHING;

-- msg-0001's history: unlinked, wrongly linked, unlinked by the revocation, then linked correctly.
INSERT INTO app.message_resolution_events (event_id, raw_message_id, mapping_id, old_clinic_id, new_clinic_id,
                                           old_status, new_status, reason, job_run_id, changed_at) VALUES
    ('90000000-0000-4000-8000-000000000001', '50000000-0000-4000-8000-000000000001', NULL, NULL, NULL,
     NULL, 'needs_review', 'No confirmed mapping', 'seed-run-1', '2026-10-18T10:05:00+08:00'),
    ('90000000-0000-4000-8000-000000000002', '50000000-0000-4000-8000-000000000001', '80000000-0000-4000-8000-000000000001',
     NULL, '10000000-0000-4000-8000-000000000003', 'needs_review', 'linked', 'Mapping confirmed', 'seed-run-2',
     '2026-10-18T11:01:00+08:00'),
    ('90000000-0000-4000-8000-000000000003', '50000000-0000-4000-8000-000000000001', '80000000-0000-4000-8000-000000000001',
     '10000000-0000-4000-8000-000000000003', NULL, 'linked', 'needs_review', 'Mapping revoked', 'seed-run-3',
     '2026-10-19T09:01:00+08:00'),
    ('90000000-0000-4000-8000-000000000004', '50000000-0000-4000-8000-000000000001', '80000000-0000-4000-8000-000000000002',
     NULL, '10000000-0000-4000-8000-000000000001', 'needs_review', 'linked', 'Mapping confirmed', 'seed-run-4',
     '2026-10-19T09:06:00+08:00')
ON CONFLICT DO NOTHING;

INSERT INTO app.clinic_field_events (event_id, clinic_id, inquiry_id, field_name, old_value, new_value,
                                     changed_by, changed_at, reason, evidence_message_ids) VALUES
    ('91000000-0000-4000-8000-000000000001', NULL, '70000000-0000-4000-8000-000000000002', 'clinic_name',
     'null', '"Meadow Clinic"', '00000000-0000-4000-8000-000000000001', '2026-10-21T10:00:00+08:00', NULL,
     '{50000000-0000-4000-8000-000000000005,50000000-0000-4000-8000-000000000006}'),
    ('91000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000001', NULL, 'contact_number',
     'null', '"0917 000 0101"', '00000000-0000-4000-8000-000000000002', '2026-10-19T10:00:00+08:00', NULL, NULL)
ON CONFLICT DO NOTHING;

INSERT INTO app.import_batches (batch_id, uploaded_by, file_sha256, original_filename, uploaded_at, state,
                                created_clinic_count, accepted_row_count, needs_review_row_count,
                                rejected_row_count, skipped_row_count) VALUES
    ('20000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002',
     encode(sha256(convert_to('synthetic-lead-import-v1', 'UTF8')), 'hex'), 'synthetic-lead-import-v1.xlsx',
     '2026-10-17T15:00:00+08:00', 'needs_review', 1, 2, 0, 1, 0)
ON CONFLICT DO NOTHING;

INSERT INTO app.import_rows (import_row_id, batch_id, sheet_name, row_number, row_fingerprint,
                             normalized_fields, validation_errors, result, clinic_id) VALUES
    ('30000000-0000-4000-8000-000000000001', '20000000-0000-4000-8000-000000000001', 'Ljs Calling Sheet', 1,
     'synthetic-fp-ljs-1', '{"clinic_name":"Riverside Clinic","contact_number":"0917 000 0301","status_code":"proposal_sent"}',
     '[]', 'accepted', '10000000-0000-4000-8000-000000000003'),
    ('30000000-0000-4000-8000-000000000002', '20000000-0000-4000-8000-000000000001', 'Jacks Calling Sheet', 2,
     'synthetic-fp-jacks-2', '{"clinic_name":"Riverside Clinic","contact_number":"0917 000 0302"}',
     '[]', 'accepted', '10000000-0000-4000-8000-000000000003'),
    ('30000000-0000-4000-8000-000000000003', '20000000-0000-4000-8000-000000000001', 'Jacks Calling Sheet', 3,
     'synthetic-fp-jacks-3', '{}', '[{"code":"missing_facility"}]', 'rejected', NULL)
ON CONFLICT DO NOTHING;

-- The two sheets disagree on Riverside's number; staff have not chosen yet, so the clinic field stays null.
INSERT INTO app.import_field_reviews (review_id, clinic_id, field_name, state) VALUES
    ('60000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000003', 'contact_number', 'unresolved')
ON CONFLICT DO NOTHING;

INSERT INTO app.import_field_review_candidates (review_id, import_row_id) VALUES
    ('60000000-0000-4000-8000-000000000001', '30000000-0000-4000-8000-000000000001'),
    ('60000000-0000-4000-8000-000000000001', '30000000-0000-4000-8000-000000000002')
ON CONFLICT DO NOTHING;

INSERT INTO app.clinic_status_events (event_id, clinic_id, old_status_code, new_status_code, origin,
                                      recorded_at, changed_by, import_row_id) VALUES
    ('92000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000003', NULL, 'proposal_sent',
     'import_baseline', '2026-10-17T15:00:00+08:00', NULL, '30000000-0000-4000-8000-000000000001'),
    ('92000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000001', NULL, 'contacted',
     'manual_create', '2026-10-18T09:00:00+08:00', '00000000-0000-4000-8000-000000000001', NULL),
    ('92000000-0000-4000-8000-000000000003', '10000000-0000-4000-8000-000000000002', NULL, 'follow_up_needed',
     'inquiry_confirmation', '2026-10-21T10:00:00+08:00', '00000000-0000-4000-8000-000000000001', NULL)
ON CONFLICT DO NOTHING;

COMMIT;
