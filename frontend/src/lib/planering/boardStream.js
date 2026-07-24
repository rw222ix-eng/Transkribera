// Live-uppbyggnad: modellen strömmar JSON tecken för tecken, så vi lagar den
// ofullständiga texten till något som går att rita innan den är färdigskriven.
// Porterad från gamla appens tryParsePartialBoard/wbCountSections.

/**
 * Försöker tolka en ofullständig JSON-tavla. Returnerar null när texten ännu
 * inte räcker till. Stänger öppna strängar och klamrar och klipper hängande
 * komma/kolon — annars vore varje halvskriven tavla oparsbar.
 */
export function parsePartialBoard(text) {
  const start = text.indexOf('{');
  if (start < 0) return null;
  const s = text.slice(start);
  try {
    return JSON.parse(s);
  } catch {
    /* faller vidare till reparationen nedan */
  }

  const stack = [];
  let inString = false;
  let escaped = false;
  for (const c of s) {
    if (inString) {
      if (escaped) escaped = false;
      else if (c === '\\') escaped = true;
      else if (c === '"') inString = false;
      continue;
    }
    if (c === '"') inString = true;
    else if (c === '{') stack.push('}');
    else if (c === '[') stack.push(']');
    else if (c === '}' || c === ']') stack.pop();
  }

  let fixed = s;
  if (inString) fixed += '"';
  fixed = fixed.replace(/[,:\s]+$/, '');
  for (let i = stack.length - 1; i >= 0; i--) fixed += stack[i];
  try {
    return JSON.parse(fixed);
  } catch {
    return null;
  }
}

/** Antal sektioner i en (möjligen ofullständig) tavla. */
export function countSections(board) {
  let n = 0;
  for (const b of (board && board.boards) || [board]) {
    if (!b) continue;
    if (b.sections) n += b.sections.length;
    for (const c of b.columns || []) n += (c.sections || []).length;
    for (const r of b.rows || []) n += (r.sections || []).length;
  }
  return n;
}
