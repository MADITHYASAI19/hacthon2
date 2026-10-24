"""Identity resolution: current & historical emails, phones, hashes, and user_id."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from code.loader import Dataset, normalize_email


def normalize_phone(p: Optional[str]) -> str:
    """Extract digits only from phone number for robust matching."""
    if not p:
        return ""
    return re.sub(r"\D", "", p)


@dataclass
class IdentitySet:
    user_id: str
    primary_email: str
    names: Set[str] = field(default_factory=set)
    emails: Set[str] = field(default_factory=set)
    phones: Set[str] = field(default_factory=set)
    phone_digits: Set[str] = field(default_factory=set)
    email_hashes: Set[str] = field(default_factory=set)

    def matches(self, text_or_dict: any) -> List[Tuple[str, str]]:
        """Check if any identifier appears in text or structured dictionary.
        
        Returns list of (identifier_type, matched_value).
        Does NOT match on names alone (to avoid look-alike collisions).
        """
        matched = []
        def visit(value):
            if isinstance(value, dict):
                for child in value.values():
                    visit(child)
                return
            if isinstance(value, (list, tuple, set)):
                for child in value:
                    visit(child)
                return
            if value is None:
                return
            v_str = str(value)
            if self.user_id and re.search(r"(?<![\w])" + re.escape(self.user_id) + r"(?![\w])", v_str):
                matched.append(("user_id", self.user_id))
            v_lower = v_str.lower()
            for em in self.emails:
                if em and em in v_lower:
                    matched.append(("email", em))
            for h in self.email_hashes:
                if h and h in v_lower:
                    matched.append(("email_hash", h))
            v_digits = re.sub(r"\D", "", v_str)
            for pd in self.phone_digits:
                if len(pd) >= 7 and pd in v_digits:
                    matched.append(("phone", pd))

        if isinstance(text_or_dict, dict):
            visit(text_or_dict)
        else:
            visit(str(text_or_dict))

        return list(set(matched))


def resolve_identity(email: str, dataset: Dataset) -> Optional[IdentitySet]:
    """Resolve full identity from email against user_identities and user_audit_log."""
    norm_email = normalize_email(email)
    user_row = dataset.email_to_user.get(norm_email)
    user_id = ""

    if user_row:
        user_id = user_row.get("user_id", "")
    else:
        # Check audit log for historical email
        for r in dataset.user_audit_log:
            if r.get("field_name") == "email":
                if normalize_email(r.get("old_value")) == norm_email or normalize_email(r.get("new_value")) == norm_email:
                    user_id = r.get("user_id", "")
                    user_row = dataset.user_id_to_identity.get(user_id)
                    break

    if not user_id:
        return None

    ident = IdentitySet(user_id=user_id, primary_email=norm_email)
    ident.emails.add(norm_email)

    # Populate from current identity row if exists
    if user_row:
        name = user_row.get("name", "").strip()
        if name:
            ident.names.add(name)
        curr_email = normalize_email(user_row.get("email"))
        if curr_email:
            ident.emails.add(curr_email)
        phone = user_row.get("phone", "").strip()
        if phone:
            ident.phones.add(phone)
            p_digits = normalize_phone(phone)
            if p_digits:
                ident.phone_digits.add(p_digits)
        h = user_row.get("email_hash", "").strip().lower()
        if h:
            ident.email_hashes.add(h)

    # Enrich with historical values from user_audit_log
    audit_rows = dataset.user_id_to_audit.get(user_id, [])
    for ar in audit_rows:
        field_name = ar.get("field_name")
        old_val = ar.get("old_value", "")
        new_val = ar.get("new_value", "")

        for val in (old_val, new_val):
            if not val:
                continue
            if field_name == "email":
                norm_e = normalize_email(val)
                if norm_e:
                    ident.emails.add(norm_e)
            elif field_name == "phone":
                val = val.strip()
                ident.phones.add(val)
                pd = normalize_phone(val)
                if pd:
                    ident.phone_digits.add(pd)
            elif field_name == "email_hash":
                h = val.strip().lower()
                if h:
                    ident.email_hashes.add(h)

    return ident
