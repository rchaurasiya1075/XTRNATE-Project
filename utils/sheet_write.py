def update_lc_excel(site, lc_name, lc_phone, handled_by="", source="auto"):
    return update_lc_excel_batch([
        {"site": site, "name": lc_name, "phone": lc_phone, "handled_by": handled_by, "source": source}
    ], source=source)


def _col_letter(i0: int) -> str:
    n = int(i0) + 1
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def apply_ticket_sync(history_gid: int, new_rows, still_open_ids):
    """Append new Incident ID rows and mark disappeared opens as Resolved on the history tab."""
    import pandas as pd

    gc, email = _client()
    ss = _retry(lambda: gc.open_by_key(XTRANET_SHEET_ID))
    ws = _ws_by_gid(ss, int(history_gid))
    values = _retry(lambda: ws.get_all_values()) or []
    if not values:
        values = [[]]
    header = [str(h).strip() for h in (values[0] if values else [])]
    if not header:
        raise RuntimeError("History tab has no header row")

    lower = {h.lower(): i for i, h in enumerate(header)}
    id_i = lower.get("incident id")
    st_i = lower.get("currentstatus", lower.get("current status"))
    rt_i = lower.get("resolved time-active", lower.get("resolved time"))
    if id_i is None:
        raise RuntimeError("Incident ID column missing on history tab")

    def nid(v):
        s = str(v or "").strip().upper()
        return "" if s in ("", "--", "NAN", "NONE", "NAT", "NULL") else s

    def is_open(v):
        t = str(v or "").strip().lower()
        if not t or t in ("--", "nan", "none") or "resolved" in t or t in ("closed", "close"):
            return False
        return "assign to fe" in t or "on hold" in t

    existing = set()
    for i, row in enumerate(values):
        if i == 0:
            continue
        if id_i < len(row):
            k = nid(row[id_i])
            if k:
                existing.add(k)

    appends = []
    if new_rows is not None and not getattr(new_rows, "empty", True):
        cmap = {str(c).strip().lower(): c for c in new_rows.columns}
        for _, rec in new_rows.iterrows():
            iid = nid(rec.get(cmap.get("incident id"), ""))
            if not iid or iid in existing:
                continue
            line = []
            for h in header:
                src = cmap.get(h.lower())
                val = rec.get(src, "") if src is not None else ""
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    val = ""
                elif str(val).lower() in ("nan", "nat", "none"):
                    val = ""
                line.append("" if val is None else str(val))
            appends.append(_pad(line, len(header)))
            existing.add(iid)

    open_ids = {nid(x) for x in (still_open_ids or set()) if nid(x)}
    now = _now()
    updates = []
    n_resolved = 0
    if st_i is not None:
        for i, row in enumerate(values):
            if i == 0:
                continue
            rid = nid(row[id_i]) if id_i < len(row) else ""
            if not rid or rid in open_ids:
                continue
            status = row[st_i] if st_i < len(row) else ""
            if not is_open(status):
                continue
            cell = f"{_col_letter(st_i)}{i + 1}"
            updates.append({"range": cell, "values": [["Resolved"]]})
            if rt_i is not None:
                prev = row[rt_i] if rt_i < len(row) else ""
                if str(prev).strip() in ("", "--", "nan", "None"):
                    updates.append({"range": f"{_col_letter(rt_i)}{i + 1}", "values": [[now]]})
            n_resolved += 1

    if appends:
        _retry(lambda: ws.append_rows(appends, value_input_option="USER_ENTERED"))
    for i in range(0, len(updates), 40):
        chunk = updates[i : i + 40]
        _retry(lambda c=chunk: ws.batch_update(c, value_input_option="USER_ENTERED"))
    return {
        "ok": True,
        "email": email,
        "appended": len(appends),
        "resolved": n_resolved,
        "error": "",
    }
