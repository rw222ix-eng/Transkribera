"""Render a single lesson to a shareable report (Markdown / print-friendly HTML).

No new dependency: Markdown is plain text; HTML is a small self-contained,
print-to-PDF-friendly page. Useful for the teacher's own reflection and for
sharing e.g. a test date or worksheet list with a class.
"""
from __future__ import annotations

import html as _html

# insights.typ -> heading, in display order.
_TYP_LABELS = [
    ("kalender", "Kalender"),
    ("svårighet", "Svårigheter"),
    ("åtgärd", "Åtgärder"),
    ("grupprum", "Grupprum"),
    ("material", "Material"),
    ("övrigt", "Övrigt"),
]


def _clock(t: float) -> str:
    s = int(t or 0)
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def _meta_pairs(lesson: dict) -> list[tuple[str, str]]:
    # `or ""`, inte default i get(): ts-kolumnen kan finnas med värdet None,
    # och None[:10] fällde hela rapporten (fuzzfynd 3).
    pairs = [("Datum", lesson.get("datum") or (lesson.get("ts") or "")[:10]),
             ("Klass", lesson.get("group")), ("Kurs", lesson.get("course")),
             ("Sal", lesson.get("sal")), ("Längd", lesson.get("dur"))]
    return [(k, v) for k, v in pairs if v]


def _grouped(insights: list[dict]) -> list[tuple[str, list[dict]]]:
    out = []
    for typ, label in _TYP_LABELS:
        items = [i for i in (insights or []) if i.get("typ") == typ]
        if items:
            out.append((label, items))
    return out


def lesson_markdown(lesson: dict, insights: list[dict],
                    markers: list[dict] | None = None) -> str:
    name = lesson.get("name") or "Lektion"
    lines = [f"# {name}", ""]
    lines.append("  ".join(f"**{k}:** {v}" for k, v in _meta_pairs(lesson)))
    lines.append("")
    lines += ["## Sammanfattning", "", (lesson.get("summary") or "—").strip(), ""]

    groups = _grouped(insights)
    if groups:
        lines += ["## Insikter", ""]
        for label, items in groups:
            lines.append(f"### {label}")
            for it in items:
                extra = []
                if it.get("ref"):
                    extra.append(str(it["ref"]))
                if it.get("due_date"):
                    extra.append("📅 " + str(it["due_date"]))
                suffix = f" ({' · '.join(extra)})" if extra else ""
                done = "~~" if it.get("status") == "klar" else ""
                lines.append(f"- {done}{it.get('text', '')}{done}{suffix}")
            lines.append("")

    if markers:
        lines += ["## Markörer", ""]
        for m in markers:
            label = m.get("label") or "Markör"
            lines.append(f"- {_clock(m.get('t', 0))} — {label}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def lesson_html(lesson: dict, insights: list[dict],
                markers: list[dict] | None = None) -> str:
    def esc(s):
        return _html.escape(str(s if s is not None else ""))

    name = esc(lesson.get("name") or "Lektion")
    meta = " · ".join(f"{esc(k)}: {esc(v)}" for k, v in _meta_pairs(lesson))
    parts = [
        "<!doctype html><html lang='sv'><head><meta charset='utf-8'>",
        f"<title>{name}</title>",
        "<style>body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;"
        "max-width:760px;margin:40px auto;padding:0 20px;color:#1a1a1a;line-height:1.55}"
        "h1{font-size:26px;margin:0 0 4px}.meta{color:#666;font-size:14px;margin-bottom:24px}"
        "h2{font-size:18px;margin:26px 0 8px;border-bottom:1px solid #eee;padding-bottom:4px}"
        "h3{font-size:15px;margin:16px 0 6px;color:#444}ul{margin:6px 0;padding-left:22px}"
        "li{margin:3px 0}.done{color:#999;text-decoration:line-through}"
        ".x{color:#888;font-size:13px}</style></head><body>",
        f"<h1>{name}</h1>",
        f"<div class='meta'>{meta}</div>" if meta else "",
        "<h2>Sammanfattning</h2>",
        f"<p>{esc((lesson.get('summary') or '—').strip())}</p>",
    ]
    groups = _grouped(insights)
    if groups:
        parts.append("<h2>Insikter</h2>")
        for label, items in groups:
            parts.append(f"<h3>{esc(label)}</h3><ul>")
            for it in items:
                extra = []
                if it.get("ref"):
                    extra.append(esc(it["ref"]))
                if it.get("due_date"):
                    extra.append("📅 " + esc(it["due_date"]))
                suffix = f" <span class='x'>({' · '.join(extra)})</span>" if extra else ""
                cls = " class='done'" if it.get("status") == "klar" else ""
                parts.append(f"<li{cls}>{esc(it.get('text', ''))}{suffix}</li>")
            parts.append("</ul>")
    if markers:
        parts.append("<h2>Markörer</h2><ul>")
        for m in markers:
            parts.append(f"<li>{esc(_clock(m.get('t', 0)))} — {esc(m.get('label') or 'Markör')}</li>")
        parts.append("</ul>")
    parts.append("</body></html>")
    return "".join(parts)
