/* ══════════ FIGURMOTORN ══════════
   Uppgifternas figurer är inte bilder som ligger någonstans — de är CeTZ-källa
   som kompileras till SVG i webbläsaren. Skälet är redigeringen: «gör vinkeln
   60° i stället» ska vara en textändring, inte en omritning. En kompilering
   kostar 4–7 ms varm, så figuren kan räknas om medan man skriver.

   Tre saker den här filen äger, och inget annat:
     1. EN Typst-instans. Kompilatorn är tung att starta (~4 s kall) och lätt att
        använda; den startas därför en gång och delas av alla figurer.
     2. Bladets typsnitt. Utan det sätts figurens etiketter i Typsts standard-
        snitt, och ett «A» i figuren ser inte ut som ett «A» i texten. Arimo är
        metriskt lik Arial och är samma snitt som bladen använder.
     3. En cache per källhash, i localStorage. Samma figur kompileras aldrig två
        gånger, och efter första besöket ritas kända figurer utan nät. */
window.Figur = (() => {
  const VER = 'typst-0.5.0-rc7-cetz-0.2.2-arimo-7';
  const NYCKEL = 'figurcache:' + VER;
  /* Kompilatorn ligger i appen, inte på jsdelivr. Transkribera är en skrivbords-
     app: en lärare som skriver ett prov på ett tåg ska få sina figurer ritade.
     Cachen nedan räckte inte som svar — den hjälper bara figurer man redan sett.
     Versionerna är exakt de prototypen pekade ut (0.5.0-rc7). */
  const VENDOR = 'vendor/typst';
  const TYPST = new URL(VENDOR + '/all-in-one-lite.bundle.js', document.baseURI).href;
  const KOMPILATOR = new URL(VENDOR + '/typst_ts_web_compiler_bg.wasm', document.baseURI).href;
  const RITARE = new URL(VENDOR + '/typst_ts_renderer_bg.wasm', document.baseURI).href;
  /* Snittet ligger i projektet, inte på ett nät: figurtexten ska sättas likadant
     även när kompilatorn hämtas från cache. */
  const SNITT = new URL('assets/typsnitt/Arimo.ttf', document.baseURI).href;

  /* ── Cachen ──
     localStorage är litet (5 MB) och SVG:erna är ~15 kB. Vi håller ett tak och
     kastar det äldsta först — en figur som föll ur cachen kompileras bara om. */
  const TAK = 120;
  let cache = null;
  function las() {
    if (cache) return cache;
    try { cache = JSON.parse(localStorage.getItem(NYCKEL) || '{}'); } catch (e) { cache = {}; }
    return cache;
  }
  function skriv() {
    try {
      const c = las();
      const nycklar = Object.keys(c);
      if (nycklar.length > TAK) {
        nycklar.sort((a, b) => (c[a].nar || 0) - (c[b].nar || 0)).slice(0, nycklar.length - TAK).forEach(k => delete c[k]);
      }
      localStorage.setItem(NYCKEL, JSON.stringify(c));
    } catch (e) { /* fullt eller avstängt — figuren kompileras då varje gång */ }
  }
  /* Kort, stabil hash av källan. Ingen kryptografi behövs: den ska bara skilja
     två olika figurer från varandra. */
  function hasha(s) {
    let h1 = 0x811c9dc5, h2 = 0x1000193;
    for (let i = 0; i < s.length; i++) {
      const c = s.charCodeAt(i);
      h1 = (h1 ^ c) * 16777619 >>> 0;
      h2 = (h2 + c * (i + 1)) >>> 0;
    }
    return h1.toString(36) + h2.toString(36);
  }

  /* ── Kompilatorn ── */
  let start = null;
  function typst() {
    if (start) return start;
    start = (async () => {
      const mod = await import(TYPST);
      const $t = mod.$typst;
      if (!$t) throw new Error('typst.ts: $typst saknas');
      /* Figurkällan börjar med `#import "@preview/cetz:0.2.2"`, och kompilatorn
         hämtar då paketet från packages.typst.org med en SYNKRON XHR mitt i
         kompileringen. Att bara lägga wasm-filerna lokalt räckte alltså inte —
         figurerna hade fortsatt kräva nät, bara tystare.

         typst.ts skapar sitt paketregister självt (HttpPackageRegistry, som ärver
         resolvePath från FetchPackageRegistry och bara byter hämtningssätt), så
         det går inte att skicka in ett eget. Men FetchPackageRegistry ÄR
         exporterad, och det räcker: byter vi resolvePath på prototypen följer
         arvingen med. Bundlen lämnas därmed orörd — den är en vendorad artefakt
         och ska gå att byta ut mot en ny version rakt av.

         paket/ innehåller hela beroendeslutningen: cetz drar in oxifmt, och
         oxifmt drar inte in något. Lägger man till en figurtyp som importerar
         ett nytt @preview-paket måste tarbollen laddas ner hit också. */
      mod.FetchPackageRegistry.prototype.resolvePath = spec =>
        new URL(`${VENDOR}/paket/${spec.name}-${spec.version}.tar.gz`, document.baseURI).href;
      /* assetUrlPrefix pekar om typsts EGNA standardsnitt (Linux Libertine, New
         Computer Modern, DejaVu Sans Mono) till vendor/typst/snitt/.
         Utan options här lägger typst.ts självt till
         `preloadRemoteFonts([], {assets:["text"]})` mot raw.githubusercontent.com
         — 14 filer, och kompileringen dör på första blockerade hämtningen. Att i
         stället sätta `assets: false` hade tagit bort dem helt, men då saknar
         figurer med matematik sitt matematiksnitt. Samma filer alltså, lokalt. */
      $t.setCompilerInitOptions({
        getModule: () => KOMPILATOR,
        beforeBuild: [mod.preloadRemoteFonts([SNITT], {
          assets: ['text'],
          assetUrlPrefix: new URL(VENDOR + '/snitt/', document.baseURI).href
        })]
      });
      $t.setRendererInitOptions({ getModule: () => RITARE });
      return $t;
    })();
    return start;
  }

  /* ── Ramen runt varje figur ──
     Sidan är «auto» i båda riktningar: figuren blir precis så stor som den ritas,
     och HTML får skala den. Marginalen är noll — luften ägs av rutan i bladet. */
  const RAM = (kropp, snitt, storlek) => `#import "@preview/cetz:0.2.2"
#set page(width: auto, height: auto, margin: 2pt, fill: none)
#set text(font: "${snitt}", size: ${storlek}pt)
#cetz.canvas(length: 1cm, {
  import cetz.draw: *
  set-style(stroke: (thickness: 0.9pt, paint: black), mark: (fill: black))
${kropp.split('\n').map(r => '  ' + r).join('\n')}
})`;

  /* ── Att göra SVG:n fristående ──
     Två saker måste rättas i det typst.ts lämnar ifrån sig innan figuren kan
     bäddas in i ett blad:

     1. Glyferna målas med `fill: var(--glyph_fill)` — en variabel som deras egen
        visare sätter och som ingen annan sida har. Utan den faller fyllningen
        tillbaka på `svg { fill: none }` och all text i figuren blir OSYNLIG:
        strecken syns, siffrorna inte. Vi sätter den till currentColor så figuren
        ärver bladets textfärg.
     2. Kompilatorn återanvänder glyfer mellan kompileringar — den räknar med att
        allt hamnar i ETT dokument. Sju figurer i sju separata svg-element gör att
        den sjunde pekar på glyfer som bara finns i den första. Vi håller därför
        ett register över alla glyfer sessionen har sett och lägger tillbaka de
        som fattas, så varje figur står för sig själv.

     Måtten byts mot 100 % så figuren följer sin ruta i bladet; viewBox styr. */
  const glyfer = new Map();
  /* text/html, inte image/svg+xml: utdatan är inte välformad XML (skripttaggen och
     några attribut är HTML-lika), och XML-parsern ger då ett parsererror-dokument
     som tyst passerar som «inget att göra». Den lämnade texten osynlig. */
  function stad(svgtext) {
    const dok = new DOMParser().parseFromString('<div>' + svgtext + '</div>', 'text/html');
    const svg = dok.querySelector('svg');
    if (!svg) return svgtext;
    svg.querySelectorAll('script').forEach(s => s.remove());
    svg.querySelectorAll('defs path[id]').forEach(p => { if (!glyfer.has(p.id)) glyfer.set(p.id, p.outerHTML); });
    let defs = svg.querySelector('defs');
    const saknade = new Set();
    svg.querySelectorAll('use').forEach(u => {
      const h = (u.getAttribute('href') || u.getAttribute('xlink:href') || '').replace('#', '');
      if (h && !svg.querySelector('[id="' + h + '"]') && glyfer.has(h)) saknade.add(h);
    });
    if (saknade.size) {
      if (!defs) { defs = dok.createElementNS('http://www.w3.org/2000/svg', 'defs'); svg.insertBefore(defs, svg.firstChild); }
      defs.insertAdjacentHTML('beforeend', [...saknade].map(h => glyfer.get(h)).join(''));
    }
    /* Etiketterna sätts i 17 pt i figurens egen värld — en figur läses på papper
       av en elev vid en bänk, och då är siffrorna på axlarna det som avgör om den
       går att läsa av. Storleken hör till figuren, skalan till bladet. Förr var det
       samma 9 pt som i bildtexten, och rutan i bladet får rätta sig efter den. */
    svg.setAttribute('role', 'img');
    /* Storleken sätts INTE här. Bladet äger höjden — en figur på ett prov är
       stor eller liten beroende på hur mycket plats sidan har, och det vet bara
       sidan. Därför lämnas height/width till CSS (--fh) och bara det som är
       figurens egen sak står inline: glyffärgerna. */
    svg.setAttribute('style', 'display:block;--glyph_fill:currentColor;--glyph_stroke:none');
    return svg.outerHTML;
  }

  async function svg(kalla, val) {
    const o = val || {};
    /* 11 pt är baslinjen för figurtext i hela appen — samma skäl som måtten i
       katalogen: figuren ska läsas på papper av en elev vid en bänk, inte zoomas
       på en skärm. */
    const full = RAM(kalla.trim(), o.snitt || 'Arimo', o.storlek || 17);
    const nyckel = hasha(full);
    const c = las();
    if (c[nyckel]) { c[nyckel].nar = Date.now(); return c[nyckel].svg; }
    const $t = await typst();
    const ut = stad(await $t.svg({ mainContent: full }));
    c[nyckel] = { svg: ut, nar: Date.now() };
    skriv();
    return ut;
  }

  /* ── Rita in i ett element ──
     Elementet bär källan i data-cetz. Medan det kompileras står platshållaren
     kvar — inget hopp i sättningen, ingen tom ruta. */
  async function rita(el) {
    if (!el || el.dataset.klar) return;
    const kalla = el.dataset.cetz || (el.querySelector('script[type="text/cetz"]') || {}).textContent;
    if (!kalla) return;
    try {
      const ut = await svg(kalla, { snitt: el.dataset.snitt, storlek: el.dataset.storlek });
      el.innerHTML = ut;
      el.dataset.klar = '';
      el.removeAttribute('data-vantar');
    } catch (e) {
      el.dataset.fel = '';
      console.warn('Figur kunde inte ritas:', e && e.message);
    }
  }

  /* Alla figurer på sidan, en efter en. Seriellt med flit: kompilatorn är en
     instans, och parallella anrop köar ändå — men seriellt går de i läsordning
     så den översta figuren syns först. */
  async function ritaAlla(rot) {
    const list = [...(rot || document).querySelectorAll('[data-cetz]:not([data-klar])')];
    for (const el of list) await rita(el);
    return list.length;
  }

  return { svg, rita, ritaAlla, hasha, RAM };
})();
