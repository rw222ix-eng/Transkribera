"""Planering — rutter för lektionstavlan (Fas 0).

Egen router i stället för fler endpoints i server.py (se planens riskavsnitt
om scope-krypning i server.py). Fas 1 bygger vidare här med
generate/refine/render-report.
"""
from __future__ import annotations

import base64
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

# Två tavlor i 2× blir ett par MB; 30 MB är väl tilltaget men stoppar missbruk.
_MAX_PNG_BYTES = 30 * 1024 * 1024
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_DATA_PREFIX = "data:image/png;base64,"


def _safe_component(raw: str, fallback: str) -> str:
    """Gör om fritext till ett ofarligt mapp-/filnamn: inga sökvägs- eller
    Windows-reserverade tecken, ingen ledande/avslutande punkt."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", raw or "").strip().strip(".")
    return name[:80] or fallback


def create_router(base: Path) -> APIRouter:
    router = APIRouter()

    @router.post("/api/planning/export")
    async def export_board(req: Request):
        """Spara en PNG-export av tavlan under
        Transkriberingar/<lektion>/planering/ — alltid under base_dir."""
        try:
            body = await req.json()
        except Exception:
            return JSONResponse({"error": "ogiltig JSON"}, status_code=400)

        data = body.get("png") or ""
        if not isinstance(data, str) or not data.startswith(_DATA_PREFIX):
            return JSONResponse(
                {"error": "png måste vara en data-URL (image/png)"},
                status_code=400)
        b64 = data[len(_DATA_PREFIX):]
        if len(b64) > _MAX_PNG_BYTES * 4 // 3 + 4:
            return JSONResponse({"error": "bilden är för stor"}, status_code=413)
        try:
            raw = base64.b64decode(b64, validate=True)
        except Exception:
            return JSONResponse({"error": "trasig base64-kodning"}, status_code=400)
        if len(raw) > _MAX_PNG_BYTES:
            return JSONResponse({"error": "bilden är för stor"}, status_code=413)
        if not raw.startswith(_PNG_MAGIC):
            return JSONResponse({"error": "innehållet är inte en PNG"}, status_code=400)

        lesson = _safe_component(str(body.get("title") or ""), "Planering")
        out_dir = base / "Transkriberingar" / lesson / "planering"
        # Bältet + hängslen: _safe_component tar bort alla sökvägstecken, och
        # den upplösta sökvägen valideras dessutom mot base_dir (parent-set,
        # inte strängprefix — jfr _under_base i server.py).
        resolved = out_dir.resolve()
        root = base.resolve()
        if resolved != root and root not in resolved.parents:
            return JSONResponse({"error": "otillåten sökväg"}, status_code=400)

        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H.%M.%S")
        path = out_dir / f"tavla {stamp}.png"
        path.write_bytes(raw)
        return {"ok": True, "path": str(path)}

    return router
