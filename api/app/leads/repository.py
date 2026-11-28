"""PostgreSQL reads overlay authoritative staff state and re-check live identity links."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.core.config import settings
from sqlalchemy import text
from app.errors import ApiError
from .pagination import decode_cursor, encode_cursor

# Never trust a published association after a mapping was revoked or corrected.
LIVE_LINK = """JOIN app.message_resolutions r ON r.raw_message_id = m.raw_message_id
 AND r.resolution_status = 'linked'
 JOIN app.clinic_source_identities a ON a.clinic_id = r.clinic_id
 AND a.source_channel = m.source_channel AND a.source_account_id = m.source_account_id
 AND a.external_participant_id = m.external_participant_id AND a.revoked_at IS NULL"""

FIELDS = [
    "contact_person",
    "contact_number",
    "email",
    "status_code",
    "next_action_date",
    "next_step",
    "calling_notes",
    "person_spoken_to",
    "region",
    "province",
    "municipality",
    "address",
]
INQUIRY_FIELDS = FIELDS[:7]


def effective_sql():
    """Read-through keeps explicit clears and new records visible before the dbt refresh."""
    shared = ", ".join("c." + f for f in FIELDS)
    inquiry = ", ".join(
        "i." + f if f in INQUIRY_FIELDS else "NULL AS " + f for f in FIELDS
    )
    return f"""
    WITH activity AS (
      SELECT r.clinic_id, max(m.source_event_at) AS last_contact_at,
             array_agg(DISTINCT m.source_channel) AS channels,
             (array_agg(si.topic ORDER BY m.source_event_at DESC NULLS LAST,
               m.source_channel,m.source_account_id,m.source_message_id,m.raw_message_id)
               FILTER (WHERE si.topic IS NOT NULL))[1] AS latest_topic
      FROM bronze.raw_messages m {LIVE_LINK}
      LEFT JOIN silver.interactions si ON si.raw_message_id=m.raw_message_id
      GROUP BY r.clinic_id
    ), effective AS (
      SELECT c.clinic_id AS lead_id, 'clinic'::text AS record_type, c.clinic_id,
        c.clinic_name, 'confirmed'::text AS clinic_name_state, {shared}, c.version,
        act.last_contact_at, coalesce(act.channels, ARRAY[]::text[]) AS channels,
        (s.lead_id IS NULL OR s.version <> c.version) AS pending_projection,
        NULL::text AS next_action, ''::text AS search_identity, act.latest_topic
      FROM app.clinics c LEFT JOIN activity act USING(clinic_id)
      LEFT JOIN silver.leads s ON s.lead_id=c.clinic_id AND s.record_type='clinic'
      UNION ALL
      SELECT i.inquiry_id, 'inquiry', NULL::uuid, NULL, 'unknown', {inquiry}, i.version,
        NULL::timestamptz, ARRAY[i.source_channel],
        (s.lead_id IS NULL OR s.version <> i.version), 'request_clinic_name',
        concat_ws(' ',i.source_channel,i.source_account_id,i.external_participant_id), NULL::text AS latest_topic
      FROM app.lead_inquiries i
      LEFT JOIN silver.leads s ON s.lead_id=i.inquiry_id AND s.record_type='inquiry'
      WHERE i.state='open'
    )"""


def metadata(conn):
    """Read the scheduler's publication ledger; a dbt staging build is never a publication.

    Return allowlisted status/timestamp fields only. Task errors, counts, DAG identifiers and
    connection details remain private pipeline internals rather than browser response fields.
    """
    rows = [
        dict(row)
        for row in conn.execute(
            text("""SELECT pipeline, last_run_status,
        last_run_started_at, last_run_finished_at, last_succeeded_at,
        last_succeeded_data_as_of FROM app.pipeline_status ORDER BY pipeline""")
        ).mappings()
    ]
    silver = next((row for row in rows if row["pipeline"] == "silver_publish"), {})
    published = silver.get("last_succeeded_data_as_of")
    now = datetime.now(timezone.utc)
    return dict(
        as_of=now,
        published_at=published,
        last_run_status=silver.get("last_run_status"),
        is_stale=bool(
            published
            and (now - published).total_seconds()
            > settings.pipeline_stale_after_minutes * 60
        ),
        stale_after_minutes=settings.pipeline_stale_after_minutes,
        pipelines=rows,
    )


def list_leads(
    conn,
    *,
    mode="all",
    status=None,
    q="",
    next_action=None,
    limit=50,
    cursor=None,
    business_date=None,
):
    """Stable keysets use normalized display name and UUID; due adds date and contact time."""
    effective_date = (
        (business_date or datetime.now(ZoneInfo("Asia/Manila")).date().isoformat())
        if mode == "due"
        else None
    )
    scope = dict(
        mode=mode,
        status=status,
        q=q,
        next_action=next_action,
        business_date=effective_date,
    )
    sort = [
        "lower(coalesce(clinic_name, 'Clinic name unknown'))",
        "record_type",
        "lead_id::text",
    ]
    if mode == "due":
        sort = [
            "next_action_date::text",
            "coalesce(to_char(last_contact_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS.US'), '9999')",
        ] + sort
    keys = decode_cursor(cursor, scope, len(sort))
    params = dict(
        status=status,
        q=q.lower(),
        next_action=next_action,
        limit=limit + 1,
        business_date=effective_date,
    )
    where = ["true"]
    if status:
        where.append("status_code=:status")
    if q:
        # strpos treats wildcard characters literally and all values remain bound parameters.
        where.append(
            "strpos(lower(concat_ws(' ', clinic_name, contact_person, contact_number, email, search_identity, lead_id::text)), :q)>0"
        )
    if next_action:
        where.append("next_action_date=CAST(:next_action AS date)")
    if mode == "due":
        where.append(
            "next_action_date <= CAST(:business_date AS date) AND status_code IS DISTINCT FROM 'closed'"
        )
    elif mode == "needs-name":
        where.append("record_type='inquiry' AND next_action_date IS NULL")
    if keys:
        params.update({f"k{i}": k for i, k in enumerate(keys)})
        where.append(
            "("
            + ",".join(sort)
            + ") > ("
            + ",".join(f":k{i}" for i in range(len(keys)))
            + ")"
        )
    query = (
        effective_sql()
        + " SELECT *, "
        + ", ".join(f"{s} AS _k{i}" for i, s in enumerate(sort))
    )
    query += (
        " FROM effective WHERE "
        + " AND ".join(where)
        + " ORDER BY "
        + ",".join(sort)
        + " LIMIT :limit"
    )
    rows = [dict(r) for r in conn.execute(text(query), params).mappings()]
    more = len(rows) > limit
    rows = rows[:limit]
    token = (
        encode_cursor(scope, [rows[-1][f"_k{i}"] for i in range(len(sort))])
        if more
        else None
    )
    for row in rows:
        row.pop("search_identity", None)
        for i in range(len(sort)):
            row.pop(f"_k{i}")
    return dict(items=rows, next_cursor=token, **metadata(conn))


def detail(conn, lead_id):
    """Return authoritative operational fields and live-link activity, or a safe missing-row error."""
    rows = (
        conn.execute(
            text(effective_sql() + " SELECT * FROM effective WHERE lead_id=:id"),
            {"id": lead_id},
        )
        .mappings()
        .all()
    )
    if not rows:
        raise ApiError(404, "not_found", "Lead not found")
    result = dict(rows[0])
    result.pop("search_identity", None)
    return result


def history(conn, lead_id, limit=50, cursor=None):
    """Page only currently authorized links, retaining raw lineage and reviewer attribution."""
    lead = detail(conn, lead_id)
    scope = {"history": str(lead_id)}
    keys = decode_cursor(cursor, scope, 5)
    params = {"id": lead_id, "limit": limit + 1}
    # Inquiry evidence belongs to its exact complete source key; incomplete identities expose only origin.
    if lead["record_type"] == "clinic":
        joins, condition = LIVE_LINK, "r.clinic_id=:id"
    else:
        joins = """JOIN app.lead_inquiries i ON i.inquiry_id=:id AND i.state='open'
          AND (m.raw_message_id=i.origin_raw_message_id OR
          (i.external_participant_id IS NOT NULL AND m.source_channel=i.source_channel
          AND m.source_account_id=i.source_account_id AND m.external_participant_id=i.external_participant_id))"""
        condition = "true"
    sort = [
        "coalesce(to_char(m.source_event_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS.US'), '9999')",
        "m.source_channel",
        "m.source_account_id",
        "m.source_message_id",
        "m.raw_message_id::text",
    ]
    if keys:
        params.update({f"k{i}": k for i, k in enumerate(keys)})
        condition += (
            " AND ("
            + ",".join(sort)
            + ") > ("
            + ",".join(f":k{i}" for i in range(5))
            + ")"
        )
    sql = """SELECT m.raw_message_id, m.source_channel AS channel, m.direction,
       m.source_event_at AS event_at, m.source_account_id, m.source_message_id,
       m.source_thread_id, left(m.parsed_payload->>'snippet', 1000) AS excerpt,
       s.topic, s.derived_status_code, rstaff.email AS staff_email, """
    sql += ", ".join(f"{s} AS _k{i}" for i, s in enumerate(sort))
    sql += f""" FROM bronze.raw_messages m {joins}
       LEFT JOIN silver.interactions s ON s.raw_message_id=m.raw_message_id
       LEFT JOIN app.message_resolutions attrib ON attrib.raw_message_id=m.raw_message_id
       LEFT JOIN app.staff_users rstaff ON rstaff.user_id=attrib.resolved_by
       WHERE {condition} ORDER BY {','.join(sort)} LIMIT :limit"""
    rows = [dict(r) for r in conn.execute(text(sql), params).mappings()]
    more = len(rows) > limit
    rows = rows[:limit]
    token = (
        encode_cursor(scope, [rows[-1][f"_k{i}"] for i in range(5)]) if more else None
    )
    for row in rows:
        for i in range(5):
            row.pop(f"_k{i}")
    return dict(
        clinic_id=lead["clinic_id"], lead_id=lead_id, items=rows, next_cursor=token
    )
