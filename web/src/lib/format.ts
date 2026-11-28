// Display helpers. Business dates follow the Asia/Manila calendar (see the API contract).
const TIME_ZONE = "Asia/Manila";

/** "11 Sep" from an ISO date or instant. */
export function formatShortDate(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    timeZone: TIME_ZONE,
  }).format(toDate(value));
}

/** "09 Sep 2026 · 14:22" from an instant. */
export function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";
  const date = toDate(value);
  const day = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: TIME_ZONE,
  }).format(date);
  const time = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: TIME_ZONE,
  }).format(date);
  return `${day} · ${time}`;
}

/** "6 min ago" relative to now. */
export function formatRelative(value: string, now = new Date()) {
  const seconds = Math.round((toDate(value).getTime() - now.getTime()) / 1000);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto", style: "short" });
  const abs = Math.abs(seconds);
  if (abs < 60) return rtf.format(seconds, "second");
  if (abs < 3600) return rtf.format(Math.round(seconds / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(seconds / 3600), "hour");
  return rtf.format(Math.round(seconds / 86400), "day");
}

// A bare YYYY-MM-DD is a Manila business date; pin it to Manila noon so it never shifts a day.
function toDate(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T12:00:00+08:00`) : new Date(value);
}
