"""Tag last-remark text for meeting analysis. One primary tag only."""

import pandas as pd

TAG_RULES = [
    ("NOT Feasible for service", [
        "not feasible", "technically not feasible", "rolled back by isp",
        "has become technically not",
    ]),
    ("Vendor Change", [
        "vendor change", "change of vendor", "vendor changed", "new vendor",
        "lm vendor", "last mile vendor", "alternate service provider",
        "alternate service", "provisioned on alternate", "existing operator",
    ]),
    ("Device Rebooted", [
        "post rebooting onu", "rebooting onu", "post reboot",
        "onu by isp with customer intervention",
    ]),
    ("ISP Change", ["isp change", "change of isp", "isp changed", "airtel to", "bsnl to", "switch isp"]),
    ("Migration", ["migration", "migrat", "link migration", "shifting", "media change", "fiber to air", "air to fiber"]),
    ("Feasibility", ["feasibility", "feasibl", "survey pending", "feasibility pending"]),
    ("Fibre Cut", ["fibre cut", "fiber cut", "ofc cut", "cable cut"]),
    ("Technical Issue", ["technical", "tech issue", "hardware", "configuration", "config issue", "device issue", "onu", "modem", "olt", "backend", "node isolation", "upstream"]),
    ("Power Issue", ["power outage", "power fail", "power issue", "no power", "electricity"]),
    ("Third Party", ["third party", "3rd party", "customer end", "bank end", "lan issue"]),
    ("Force Majeure", ["force maj", "rain", "flood", "landslide", "natural calamity", "storm"]),
    ("Pending Confirmation", ["confirmation pending", "link up confirmation", "customer confirmation"]),
    ("FE Visit", ["fe will visit", "fe visit", "visit at site", "engineer visit"]),
]


def tag_remark(text):
    t = str(text or "").lower()
    if not t or t in ("nan", "none", "--"):
        return ["Unclassified"]
    # first match only — no double count
    for name, keys in TAG_RULES:
        if any(k in t for k in keys):
            return [name]
    return ["Others"]


def primary_tag(text):
    tags = tag_remark(text)
    return tags[0]


def apply_tags(df, reason_col="reason"):
    out = df.copy()
    src = out[reason_col] if reason_col in out.columns else pd.Series("", index=out.index)
    out["remark_tag"] = src.apply(primary_tag)
    out["remark_tags"] = out["remark_tag"]
    return out


def dt_hrs(row):
    if "down_time_min" in row.index and pd.notna(row.get("down_time_min")):
        try:
            return round(float(row["down_time_min"]) / 60.0, 2)
        except Exception:
            pass
    if pd.notna(row.get("submitted_time")) and pd.notna(row.get("resolved_time")):
        try:
            return round((row["resolved_time"] - row["submitted_time"]).total_seconds() / 3600.0, 2)
        except Exception:
            return None
    return None
