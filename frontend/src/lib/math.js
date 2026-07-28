// Typsätter $…$ i ett elements text med den vendrade KaTeX:en. Porterad ur
// gamla appens renderMathIn (app/web/static/app.js:4268-4285). Obalanserade
// $ lämnas som text, och ett KaTeX-fel faller tillbaka på råtexten — en
// trasig formel får aldrig sänka kortet.
//
// AVVIKELSE MOT GAMLA APPEN, med flit: renderMathIn läser om elementets
// textContent vid varje pass, för morphdom skriver tillbaka råtexten i DOM:en
// före varje omrendering. Svelte gör inte det. Svelte äger en TEXTNOD inuti
// elementet, och när vi sätter innerHTML kopplas den noden loss ur trädet —
// Svelte fortsätter skriva till den, osynligt. Ett andra pass som läser
// textContent skulle då se den redan satta matematiken (inga $ kvar), hoppa
// över, och kortet skulle visa GAMMAL uppgiftstext efter en ändring.
// Verifierat i webbläsaren 2026-07-25: servern svarade "… (ändrad)" medan
// kortet fortfarande visade den gamla texten.
// Därför utgår typsättningen här alltid från texten som skickas in, och
// elementets innehåll skrivs alltid av oss.

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

/** KaTeX laddas som en global via en <script>-tagg i index.html, inte som
 *  modul — därför den här lilla castningen i stället för en import. */
function katexLib() {
  return /** @type {any} */ (window).katex;
}

/**
 * Typsätter `text` in i `el`. Tyst no-op när KaTeX inte är laddad — då står
 * texten kvar som Svelte renderade den, alltså rå LaTeX i stället för ett
 * tomt kort.
 *
 * @param {HTMLElement} el
 * @param {string} [text] texten som ska sättas. Utelämnas den läses
 *   elementets nuvarande textContent (bara vettigt före första passet).
 */
export function typeset(el, text) {
  const katex = katexLib();
  if (!katex || !el) return;
  const txt = text ?? el.textContent ?? '';
  const parts = txt.split('$');
  // Ingen eller obalanserad $ — lämna texten som text, men skriv den ändå:
  // elementet kan bära satt matematik från ett tidigare pass.
  if (parts.length < 3) {
    if (el.textContent !== txt) el.textContent = txt;
    return;
  }
  let html = '';
  for (let i = 0; i < parts.length; i++) {
    if (i % 2 === 0 || i === parts.length - 1) {
      html += escapeHtml(parts[i]);
      continue;
    }
    try {
      html += katex.renderToString(parts[i], { throwOnError: false, output: 'html' });
    } catch {
      html += escapeHtml('$' + parts[i] + '$');
    }
  }
  el.innerHTML = html;
}

/**
 * Attachment-fabrik: typsätter vid montering och när `text` ändras.
 * Använd som <p {@attach typsattning(uppgift.text)}>{uppgift.text}</p> — texten
 * står kvar i markupen så den syns även utan KaTeX.
 *
 * Var en `use:`-action förut. Attachmentet ÄR omtypsättningen: Svelte kör om
 * funktionen när något den läser ändras, och `text` läses här i fabriken. Det
 * gör actionens separata `update`-gren överflödig — samma beteende, ett
 * kodstycke mindre att hålla i synk.
 *
 * @param {string} text uppgiftstexten.
 * @returns {(el: HTMLElement) => void}
 */
export function typsattning(text) {
  return (el) => typeset(el, text);
}
