// Tunn API-klient mot FastAPI. Samma endpoints som den gamla appen använder;
// streamPost speglar serverns SSE-kontrakt (app/web/sse.py):
//   data: {"type":"log"|"token"|"done"|"error", ...}\n\n
const JSON_HEADERS = { 'Content-Type': 'application/json' };

/** GET som JSON. Kastar vid HTTP-fel. */
export async function getJSON(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

/** POST som JSON. Kastar med serverns felmeddelande när det finns. */
export async function postJSON(url, body = {}) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
  let data = null;
  try {
    data = await resp.json();
  } catch {
    data = null;
  }
  if (!resp.ok || (data && data.error)) {
    throw new Error((data && data.error) || `HTTP ${resp.status}`);
  }
  return data;
}

/**
 * POST med RÅ textkropp — inte JSON. Kalenderns klientfilsinstallation
 * (POST /api/calendar/client-secret) vill ha filens INNEHÅLL som kropp;
 * servern gör `json.loads(raw)` på hela requestkroppen själv
 * (app/web/server.py:1363-1379). postJSON hade lindat innehållet i ännu ett
 * lager JSON-strängifiering och gett en trasig kropp.
 */
export async function postRaw(url, text) {
  const resp = await fetch(url, { method: 'POST', body: text });
  let data = null;
  try {
    data = await resp.json();
  } catch {
    data = null;
  }
  if (!resp.ok || (data && data.error)) {
    throw new Error((data && data.error) || `HTTP ${resp.status}`);
  }
  return data;
}

/**
 * POST som streamar SSE-events. `onEvent` anropas per event.
 * Fel — både HTTP-fel och avbrott — levereras som {type:'error', message}
 * i stället för att kastas, så anroparen har ett enda felställe.
 */
export async function streamPost(url, body, onEvent) {
  let resp;
  try {
    resp = await fetch(url, {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
  } catch (e) {
    onEvent({ type: 'error', message: String(e?.message || e) });
    return;
  }

  if (!resp.ok) {
    let message = `HTTP ${resp.status}`;
    try {
      const j = await resp.json();
      if (j && j.error) message = j.error;
    } catch {
      /* behåll HTTP-statusen */
    }
    onEvent({ type: 'error', message });
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let sawTerminal = false;
  try {
    // getReader() ligger innanför try:t — annars kan ett saknat resp.body kasta
    // förbi anroparens enda felställe (kontraktet är att fel alltid kommer via onEvent).
    const reader = resp.body.getReader();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop() ?? '';
      for (const chunk of parts) {
        const line = chunk.split('\n').find((l) => l.startsWith('data:'));
        if (!line) continue;
        // Endast parsningen är skyddad — ett fel som kastas inne i onEvent ska
        // inte tystas här, annars hänger anroparen kvar i 'running' för alltid.
        let ev;
        try {
          ev = JSON.parse(line.slice(5).trim());
        } catch {
          continue; // ofullständigt event — hoppa över
        }
        if (ev.type === 'done' || ev.type === 'error') sawTerminal = true;
        onEvent(ev);
      }
    }
    if (!sawTerminal) {
      onEvent({ type: 'error', message: 'Anslutningen till servern bröts.' });
    }
  } catch (e) {
    if (!sawTerminal) {
      onEvent({ type: 'error', message: String(e?.message || e) });
    }
  }
}
