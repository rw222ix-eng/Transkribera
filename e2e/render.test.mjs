/* Enhetstester för de rena renderar-funktionerna i app/web/static/app.js:
 * Markdown/LaTeX-chattrenderaren (renderRich/renderRichInline) och _videoThumb.
 *
 * app.js är en IIFE utan exporter, så funktionerna extraheras ur källan och
 * evalueras i en sandlåda (de är DOM-fria och beror bara på esc + konstanttabeller).
 * Körs fristående:  node e2e/render.test.mjs   (exit != 0 vid fel).
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(__dirname, '..', 'app', 'web', 'static', 'app.js'), 'utf8');

function between(from, to) {
  const a = src.indexOf(from), b = src.indexOf(to);
  if (a < 0 || b < 0 || b < a) throw new Error(`Kunde inte extrahera "${from}" .. "${to}" ur app.js`);
  return src.slice(a, b);
}
const escSrc = (() => { const a = src.indexOf('function esc(s)'); return src.slice(a, src.indexOf('\n', a)); })();
const rendererSrc = between('var _GREEK =', 'function fmtStorage');   // _GREEK … renderRich
const videoSrc = between('function extOf(n)', 'function qName(');     // extOf, VIDEO_EXT, _videoThumb

const api = new Function(`"use strict";
${escSrc}
${rendererSrc}
${videoSrc}
return { esc, renderMath, renderRich, renderRichInline, _videoThumb };`)();
const { renderRich, renderRichInline, _videoThumb } = api;

let pass = 0, fail = 0;
function ok(name, cond) { if (cond) pass++; else { fail++; console.error('FAIL:', name); } }
function has(name, html, needle) { ok(name, html.includes(needle)); }
function hasnt(name, html, needle) { ok(name, !html.includes(needle)); }

// --- Markdown + LaTeX ---
has('fetstil', renderRich('**hej**'), '<strong>hej</strong>');
has('inline-kod', renderRich('`kod`'), '<code class="md-code">kod</code>');
has('brak', renderRich('$\\frac{1}{2}$'), 'mfrac');
has('rot', renderRich('$\\sqrt{2}$'), 'msqrt');
has('exponent', renderRichInline('$x^2$'), '<sup>');
has('index', renderRichInline('$a_1$'), '<sub>');
has('display-matte', renderRich('$$x+1$$'), 'math-d');
{ const ul = renderRich('- a\n- b'); ok('lista', ul.includes('<ul class="md-list">') && (ul.match(/<li>/g) || []).length === 2); }
has('rubrik', renderRich('# Rubrik'), 'md-h');

// --- XSS: all text escapas, aldrig rå HTML ---
hasnt('xss-html-escapad', renderRich('<img src=x onerror=alert(1)>'), '<img');
has('xss-html-escapad-till-entitet', renderRich('<img src=x onerror=alert(1)>'), '&lt;img');
hasnt('xss-i-matte', renderRichInline('$<b>x</b>$'), '<b>');

// --- Siffror/belopp i text lämnas orörda (#13) ---
{ const o = renderRichInline('Jag har $5 och $10'); ok('belopp-ej-matte', !o.includes('class="math"') && o.includes('$5') && o.includes('$10')); }

// --- Kod skyddas FÖRE matte: dollartecken i kod tolkas inte som matte (#12) ---
{ const o = renderRich('`a$b$c`'); ok('inline-kod-med-dollar', o.includes('<code class="md-code">a$b$c</code>') && !o.includes('class="math"')); }
{ const o = renderRich('```\npris = $5\n```'); ok('kodblock-med-dollar', o.includes('pris = $5') && !o.includes('class="math"')); }

// --- Äkta matte fungerar fortfarande bredvid vanlig text ---
has('matte-i-lopande-text', renderRichInline('Lös $x^2 = 4$ nu'), '<sup>');

// --- _videoThumb: bara riktiga videofiler får en thumbnail ---
ok('mp4-thumb', _videoThumb({ video: { path: 'C:/v/a.mp4', ext: 'mp4' } }) === '/api/thumb?path=' + encodeURIComponent('C:/v/a.mp4'));
ok('mkv-thumb', _videoThumb({ video: { path: 'C:/v/a.mkv', ext: 'mkv' } }) !== null);
ok('mov-ext-fran-namn', _videoThumb({ video: { path: 'C:/v/a', name: 'film.mov' } }) !== null);
ok('wav-ingen-thumb', _videoThumb({ video: { path: 'C:/v/a.wav', ext: 'wav' } }) === null);
ok('mp3-ingen-thumb', _videoThumb({ video: { path: 'a.mp3', ext: 'mp3' } }) === null);
ok('webm-som-ljud', _videoThumb({ video: { path: 'C:/v/a.webm', ext: 'webm' } }) === null);
ok('ingen-video', _videoThumb({}) === null);
ok('video-utan-path', _videoThumb({ video: { ext: 'mp4' } }) === null);

console.log(`render.test: ${pass} passerade, ${fail} misslyckades`);
if (fail) process.exit(1);
