"""python -m app.web — start the local web UI and open the browser."""
from __future__ import annotations
import os
import threading
import time
import webbrowser

import uvicorn

from app import debug_log
from app.web import port as port_kalla
from app.web import portvakt
from app.web.server import create_app


def main() -> None:
    # Samma portkälla och samma vakt som fönsterstarten (app/web/port.py,
    # app/web/portvakt.py). Kopian av _free_port som stod här gled isär från
    # desktop.py:s: 2026-09-06 låg båda i ett spann Windows reserverat.
    portvakt.kolla(port_kalla.FORSTAHAND, debug_log.get_logger())
    port, _hinder = port_kalla.ledig_port()
    url = f"http://127.0.0.1:{port}"
    # Samma stämpel som desktop-starten sätter: den här vägen ÄR appen, bara i
    # en vanlig flik i stället för i fönstret. Se app/web/server.py, _hus.
    os.environ["TRANSKRIBERA_START"] = "webb"
    os.environ["TRANSKRIBERA_PORT"] = str(port)
    app = create_app()

    def open_browser():
        time.sleep(1.0)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()
    print(f"Transkribera web: {url}  (Ctrl+C för att stänga)")
    # Språkmodellen startas per fråga av Claude Code (app/claude_code.py) och
    # lämnar ingen process efter sig. Avslutningsanropet står kvar som en enda
    # väg ut ur allt appen kan ha startat.
    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    finally:
        app.state.arbiter.stop_llm()


if __name__ == "__main__":
    main()
