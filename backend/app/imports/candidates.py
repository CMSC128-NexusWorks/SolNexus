"""Find possible duplicate clinics among import rows and existing clinics, for staff review (candidates-v1).

The contract requires surfacing exact normalized-name collisions, shared nonblank contact identifiers and
plausible differently written names, across both sheets and app.clinics. Rows of earlier uploads that
still await a staff decision are compared too, since they have no clinic to match yet. A candidate is never an identity
decision: a row with any candidate is held as needs_review until staff decide, and nothing here merges.

Signals (basis codes), all exact matches on a normalized key, so each one is explainable to staff:

* exact_name    names equal after Unicode normalization, case folding and punctuation/space removal.
                "St. Luke's  Clinic" == "st lukes clinic".
* similar_name  names equal once generic words (clinic, medical, center, ...) and spaces are also
                dropped: "Harborview Medical Clinic" ~ "Harbor View Clinic". Reported only when the names
                are not already an exact_name match.
* shared_email  the same email, case-insensitive.
* shared_phone  the same last 10 digits, so "0917 000 0101", "+63 917 000 0101" and 9170000101 agree.
                Numbers with fewer than 10 digits are too short to suggest identity and are ignored.

No edit-distance or similarity threshold is used: the contract says no threshold is approved yet, and a
tuned number would hide why two rows were paired. Typos that survive these keys ("Harborveiw") are not
caught; staff reconcile those before production migration, as the contract requires.

Lookups are hash-index joins, so a 10,000-row upload against thousands of clinics stays linear.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Hashable, Iterable
from dataclasses import dataclass

VERSION = "candidates-v1"

# Words that describe the kind of facility rather than which one it is. Kept short on purpose: every word
# added here makes more distinct clinics look alike (they still only reach review, never a merge).
GENERIC_NAME_WORDS = frozenset(
    {"clinic", "clinics", "medical", "center", "centre", "hospital", "the", "of", "and", "inc", "corp",
     "corporation", "co", "company", "ltd"}
)
_NON_ALNUM = re.compile(r"[^0-9a-z]+")
_COMBINING = re.compile(r"[̀-ͯ]")
PHONE_DIGITS = 10


def name_key(name: str | None) -> str | None:
    if not name:
        return None
    # NFKD then dropping combining marks folds "Peñafrancia" to "penafrancia"; NFKC-style compatibility
    # folding also turns full-width letters into ASCII.
    text = _COMBINING.sub("", unicodedata.normalize("NFKD", name)).casefold()
    text = text.replace("&", " and ").replace("'", "").replace("’", "")
    words = _NON_ALNUM.sub(" ", text).split()
    return " ".join(words) or None


def loose_name_key(name: str | None) -> str | None:
    exact = name_key(name)
    if exact is None:
        return None
    # An all-generic name ("Medical Clinic") has no distinguishing word left; it must not pair with others.
    return "".join(word for word in exact.split() if word not in GENERIC_NAME_WORDS) or None


def email_key(email: str | None) -> str | None:
    return (email.strip().casefold() or None) if email else None


def phone_key(phone: str | None) -> str | None:
    digits = re.sub(r"\D", "", phone or "")
    return digits[-PHONE_DIGITS:] if len(digits) >= PHONE_DIGITS else None


@dataclass(frozen=True)
class CandidateKeys:
    name: str | None
    loose_name: str | None
    email: str | None
    phone: str | None

    @classmethod
    def from_fields(cls, fields: dict) -> CandidateKeys:
        return cls(
            name=name_key(fields.get("clinic_name")),
            loose_name=loose_name_key(fields.get("clinic_name")),
            email=email_key(fields.get("email")),
            phone=phone_key(fields.get("contact_number")),
        )


# A candidate target is ("row", <row ref>) for another row in this upload, ("clinic", <clinic_id>), or
# ("pending", <import_row_id>) for a row of an earlier batch that still awaits a staff decision.
Target = tuple[str, Hashable]


def find_candidates(
    rows: Iterable[tuple[Hashable, CandidateKeys]],
    clinics: Iterable[tuple[Hashable, CandidateKeys]],
    pending: Iterable[tuple[Hashable, CandidateKeys]] = (),
) -> dict[Hashable, dict[Target, list[str]]]:
    """For each row ref, the other rows, existing clinics and pending rows it may duplicate, with sorted
    basis codes.

    Rows with no candidate are absent from the result. Symmetric between rows of this upload: if row a
    lists row b, row b lists row a, so the outcome cannot depend on sheet or processing order. Pending rows
    of earlier batches are targets only: they have no clinic yet, so without them an overlapping upload
    would create a clinic that staff then create again when they decide the earlier batch.
    """
    rows = list(rows)
    index: dict[tuple[str, str], list[Target]] = defaultdict(list)
    for kind, entries in (("row", rows), ("clinic", clinics), ("pending", pending)):
        for ref, keys in entries:
            for signal, value in (("name", keys.name), ("loose", keys.loose_name), ("email", keys.email),
                                  ("phone", keys.phone)):
                if value is not None:
                    index[(signal, value)].append((kind, ref))

    found: dict[Hashable, dict[Target, set[str]]] = {}
    for ref, keys in rows:
        matches: dict[Target, set[str]] = defaultdict(set)
        for signal, value, basis in (("name", keys.name, "exact_name"), ("loose", keys.loose_name, "similar_name"),
                                     ("email", keys.email, "shared_email"), ("phone", keys.phone, "shared_phone")):
            if value is None:
                continue
            for target in index[(signal, value)]:
                if target != ("row", ref):
                    matches[target].add(basis)
        for basis in matches.values():
            if "exact_name" in basis:
                basis.discard("similar_name")
        if matches:
            found[ref] = matches
    return {ref: {target: sorted(basis) for target, basis in matches.items()} for ref, matches in found.items()}


def review_groups(candidates: dict[Hashable, dict[Target, list[str]]]) -> dict[Hashable, Hashable]:
    """Map each row with candidates to its review group: rows of this upload connected through row-to-row
    candidates. Pending rows of earlier batches belong to their own batch's groups and are not joined.

    Staff decide a group together so that, when they confirm two rows are one new clinic, conflicting
    values from both are seen at once and neither sheet wins by being decided first. The group key is the
    smallest row ref in the group, so it is stable for a given batch.
    """
    parent: dict[Hashable, Hashable] = {ref: ref for ref in candidates}

    def root(ref: Hashable) -> Hashable:
        while parent[ref] != ref:
            parent[ref] = parent[parent[ref]]
            ref = parent[ref]
        return ref

    for ref, matches in candidates.items():
        for kind, other in matches:
            if kind == "row":
                a, b = root(ref), root(other)
                if a != b:
                    parent[max(a, b)] = min(a, b)
    return {ref: root(ref) for ref in candidates}
