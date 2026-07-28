<script>
  // Ett lektionskort. Speglar app.js:4917-4946 funktionellt, omstylat till
  // designsystemet. Att öppna lektionen kom i plan B2, lektionschatten i B4.
  import { kursFarg } from './kursfarg.js';
  // Action:en importeras DIREKT i stället för att komma som prop, till
  // skillnad från onRedigera och onRadera. De muterar Inspelningar-vyns egen
  // store och hör därför hemma hos vyn; transkriptvyn är en global modal som
  // ingen flik äger. Dessutom kommer kortets props från InspelningarView.svelte,
  // som ägs av ström B — en prop till hade krävt en ändring i deras fil.
  import { oppnaTranskriptFor } from '../transkript/actions.js';
  // Samma skäl som ovan: lektionschatten är också en global modal, och dess
  // action kommer därför direkt i stället för som en prop genom vyn.
  import { oppnaLektionschatt } from '../lektionschatt/actions.js';

  let { l, onRedigera, onRadera } = $props();

  const farg = $derived(kursFarg(l));
  const etikett = $derived(
    l.group ? l.group + (l.course ? ' · ' + l.course : '') : (l.course || 'Ej tilldelad'),
  );
  // Samma villkor som etiketten faller tillbaka på — skrivet en gång, läst
  // två gånger, så texten och knappgrindningen inte kan glida isär.
  const otilldelad = $derived(!l.group && !l.course);
  const meta = $derived([l.dur, l.model, l.lang].filter(Boolean).join(' · '));

  // Bara VIDEO-källor får miniatyr. Ljudfiler har också en spelbar mediapost,
  // så det avgörs på filändelsen. Listan är VIDEO_EXT ur _videoThumb
  // (app.js:433) ordagrant — INTE app/media.py:39:s VIDEO_EXTS, som är en
  // annan lista med ett annat syfte.
  //
  // webm saknas MEDVETET: det är appens eget LJUDinspelningsformat
  // (audio/webm;codecs=opus, plan A4). En sådan fil har ingen videoström, så
  // /api/thumb → make_thumbnail → ffmpeg misslyckas, svarar 404, och kortet
  // får en trasig <img>. Det drabbar varje lektion läraren spelat in i appen.
  const VIDEO = ['mp4', 'm4v', 'mkv', 'mov', 'avi', 'mpg', 'mpeg', 'wmv', 'flv', 'ts', 'mts'];
  const miniatyr = $derived.by(() => {
    const p = l.recording_path || '';
    const ext = (/\.([^.\\/]+)$/.exec(p) || [, ''])[1].toLowerCase();
    return VIDEO.includes(ext) ? '/api/thumb?path=' + encodeURIComponent(p) : '';
  });

  // RESERVLÄGET. Filändelsen säger bara att filen BORDE ha en videoström —
  // den säger ingenting om huruvida /api/thumb faktiskt lyckas. make_thumbnail
  // behöver ffmpeg, och saknas det (eller är filen flyttad, låst eller trasig)
  // svarar servern 404. Utan reservläge blev det en tom ruta i kortets fulla
  // bredd med aspect-ratio 16/9 — inget att se, inget att förklara, och
  // kortanatomin skilde sig dessutom från grannkortet utan miniatyr.
  //
  // Sparas som den URL som FÖLL, inte som en boolean: byter lektionen
  // recording_path (en redigering, en omhämtning) pekar jämförelsen nedan på
  // en ny URL och miniatyren får ett nytt försök helt utan $effect. En
  // boolean hade fastnat i falskt läge tills komponenten monterades om.
  let trasigTumme = $state('');
  const visaTumme = $derived(!!miniatyr && trasigTumme !== miniatyr);
</script>

<!--
  EN RAD, inte ett kort i ett rutnät. Kartoteket var tidigare
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)) med ramade,
  ytfärgade kort — precis det DESIGN.md förbjuder ("this is not a card-grid
  system", "no hero-metric tiles, no nested cards") och den enda vy i appen
  som läste som en SaaS-admin.

  Raden löser fyra fynd samtidigt: kortrutnätet självt, den tomma miniatyrytan
  (miniatyren är nu en liten ruta i radens vänsterkant i stället för ett fält i
  full bredd), Raderas vikt (handlingarna ligger i en tyst grupp till höger i
  stället för i ett 2×2-rutnät där destruktivt väger lika tungt som primärt),
  och att lektionerna kom långt ned i vyn — en rad är ungefär en tredjedel så
  hög som kortet var.

  Mönstret är inte uppfunnet här: Agenda.svelte i SAMMA vy bytte redan
  "gamla appens rutor med egen ram" mot hårlinjer mellan raderna
  (Agenda.svelte:178). Kartoteket följer nu sin granne.

  SEPARATORN ÄGS AV LISTAN, inte av raden: Kartotek.svelte ritar hårlinjen
  mellan .hylsa-syskon. En rad som bär sin egen border-top dubblerar
  grupprubrikens border-bottom på den första raden i varje vecka.
-->
<article class="kort">
  {#if visaTumme}
    <!-- alt="" med flit: miniatyren är dekor, hela innehållet står i texten
         nedanför. onerror fäller den till textlayouten i stället för att lämna
         en tom ruta — se kommentaren vid trasigTumme. -->
    <img
      class="tumme"
      src={miniatyr}
      alt=""
      loading="lazy"
      onerror={() => (trasigTumme = miniatyr)}
    />
  {/if}
  <div class="text">
    <p class="datum">{l.date || l.datum || ''}</p>
    <h3 class="namn">{l.name || '(namnlös)'}</h3>
    <!--
      "Ej tilldelad" stod tidigare som en död etikett på varje rad utan att
      något förklarade var man tilldelar. Saknas klass och kurs är taggen
      numera en KNAPP rakt in i redigeringen — samma dialog som Redigera
      öppnar, alltså ingen ny väg, bara den befintliga där frågan uppstår.

      Bara i det otilldelade fallet. En rad som REDAN bär "9A · Matematik 2b"
      säger något sant och ska förbli text; att göra även den klickbar hade
      lagt ett andra, otydligare Redigera på varje rad.
    -->
    {#if otilldelad}
      <button
        type="button"
        class="tagg tilldela"
        data-cc={farg}
        onclick={() => onRedigera(l)}
      >{etikett} — tilldela</button>
    {:else}
      <p class="tagg" data-cc={farg}>{etikett}</p>
    {/if}
    <p class="meta">{meta}{l.sal ? ' · ' + l.sal : ''}</p>
  </div>
  <!--
    RADERA STÅR FÖR SIG. Tidigare låg de fyra knapparna i ett 2×2-rutnät där
    "Radera" hade exakt samma yta och ram som "Öppna" — destruktivt och
    primärt vägde lika. Nu är de tre ofarliga textknappar i en grupp, och
    raderingen skiljs av en hårlinje och bär sin färg först vid hover/fokus.
    Formen skriker inte, men den är fortfarande omöjlig att missa när man
    letar efter den.
  -->
  <div class="knappar">
    <button type="button" class="tyst" onclick={() => oppnaTranskriptFor(l.history_id, l.name)}>Öppna</button>
    <button type="button" class="tyst" onclick={() => oppnaLektionschatt(l)}>Fråga</button>
    <button type="button" class="tyst" onclick={() => onRedigera(l)}>Redigera</button>
    <button type="button" class="tyst fara" onclick={() => onRadera(l)}>Radera</button>
  </div>
</article>

<style>
  /* Ingen ram, ingen ytfärg, inga hörn: raden bärs av hårlinjen mellan
     syskonen (Kartotek.svelte) och av luften runt texten. Flat-by-Default. */
  .kort {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px 0;
  }
  /* Miniatyren är en liten ruta i vänsterkanten, inte ett fält i full bredd.
     Faller /api/thumb bort helt (visaTumme) hoppar raden bara ihop — ingen
     tom yta står kvar, och rader med och utan video ser ut som varandra. */
  .tumme {
    flex: 0 0 auto;
    display: block;
    width: 72px;
    aspect-ratio: 16 / 9;
    object-fit: cover;
    border-radius: 3px;
    background: var(--sunken);
  }
  .text {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .datum {
    font-size: 0.72rem;
    color: var(--ink-3);
    margin: 0;
  }
  .namn {
    font-family: var(--sans);
    font-size: 1.03rem;
    font-weight: 600;
    line-height: 1.3;
    color: var(--ink);
    margin: 0;
    overflow-wrap: anywhere;
  }
  .tagg {
    align-self: flex-start;
    max-width: 100%;
    font-family: inherit;
    font-size: 0.72rem;
    font-weight: 500;
    border-radius: 3px;
    padding: 2px 8px;
    margin: 2px 0 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  /* Knappvarianten ärver taggens form helt — den ska läsas som samma sak,
     bara tryckbar. Understrykningen vid hover är enda skillnaden i vila. */
  .tilldela { border: 1px solid transparent; cursor: pointer; }
  .tilldela:hover { text-decoration: underline; text-underline-offset: 2px; }
  .meta {
    font-size: 0.72rem;
    color: var(--ink-3);
    margin: 0;
    font-variant-numeric: tabular-nums;
  }

  /* Kurs-färgchipsen. Porterade ordagrant ur app/web/static/style.css:201-206 —
     samma color-mix, samma tokennamn, samma procent. Enda skillnaden är att de
     bor här i stället för i det globala arket, så kartoteket bär sina egna
     färger i stället för att luta sig mot den gamla appens CSS. */
  [data-cc] { border: 1px solid transparent; }
  [data-cc="sky"] { background: color-mix(in srgb, var(--c-sky) 14%, transparent); color: var(--c-sky); }
  [data-cc="sage"] { background: color-mix(in srgb, var(--c-sage) 16%, transparent); color: var(--c-sage); }
  [data-cc="plum"] { background: color-mix(in srgb, var(--c-plum) 14%, transparent); color: var(--c-plum); }
  [data-cc="mustard"] { background: color-mix(in srgb, var(--c-mustard) 18%, transparent); color: var(--c-mustard); }
  [data-cc="none"] { background: var(--sunken); color: var(--ink-3); border-color: var(--line); }

  .knappar {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    gap: 14px;
  }
  /* Textknappar utan ram. Fyra ramade knappar per rad hade gett kartoteket
     tillbaka den chrome hårlinjeraden just tog bort. */
  .tyst {
    background: transparent;
    border: none;
    padding: 4px 0;
    color: var(--ink-2);
    font-family: inherit;
    font-size: 0.72rem;
    cursor: pointer;
  }
  .tyst:hover { color: var(--ink); }
  /* Raderingen skiljs av en hårlinje och bär --bad först vid hover/fokus:
     synlig när man letar, tyst när man inte gör det. Färg är dessutom inte
     ensam bärare av att den är farlig — separatorn och ordet är det. */
  .fara {
    margin-left: 4px;
    padding-left: 18px;
    border-left: 1px solid var(--line);
    color: var(--ink-3);
  }
  .fara:hover,
  .fara:focus-visible { color: var(--bad); }
</style>
