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

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop() ?? '';
      for (const chunk of parts) {
        const line = chunk.split('\n').find((l) => l.startsWith('data:'));
        if (!line) continue;
        try {
          onEvent(JSON.parse(line.slice(5).trim()));
        } catch {
          /* ofullständigt event — hoppa över */
        }
      }
    }
  } catch (e) {
    onEvent({ type: 'error', message: String(e?.message || e) });
  }
}
