<script>
  // Ett lektionskort. Speglar app.js:4917-4946 funktionellt, omstylat till
  // designsystemet. Att öppna lektionen kom i plan B2; lektionschatten kommer
  // i B4.
  import { kursFarg } from './kursfarg.js';
  // Action:en importeras DIREKT i stället för att komma som prop, till
  // skillnad från onRedigera och onRadera. De muterar Inspelningar-vyns egen
  // store och hör därför hemma hos vyn; transkriptvyn är en global modal som
  // ingen flik äger. Dessutom kommer kortets props från InspelningarView.svelte,
  // som ägs av ström B — en prop till hade krävt en ändring i deras fil.
  import { oppnaTranskriptFor } from '../transkript/actions.js';

  let { l, onRedigera, onRadera } = $props();

  const farg = $derived(kursFarg(l));
  const etikett = $derived(
    l.group ? l.group + (l.course ? ' · ' + l.course : '') : (l.course || 'Ej tilldelad'),
  );
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
</script>

<article class="kort">
  {#if miniatyr}
    <img class="tumme" src={miniatyr} alt="" loading="lazy" />
  {/if}
  <p class="datum">{l.date || l.datum || ''}</p>
  <h3 class="namn">{l.name || '(namnlös)'}</h3>
  <p class="tagg" data-cc={farg}>{etikett}</p>
  <p class="meta">{meta}{l.sal ? ' · ' + l.sal : ''}</p>
  <div class="knappar">
    <button type="button" class="ghost" onclick={() => oppnaTranskriptFor(l.history_id, l.name)}>Öppna</button>
    <button type="button" class="ghost" onclick={() => onRedigera(l)}>Redigera</button>
    <button type="button" class="ghost fara" onclick={() => onRadera(l)}>Radera</button>
  </div>
</article>

<style>
  .kort {
    display: flex;
    flex-direction: column;
    gap: 6px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 14px 15px;
    overflow: hidden;
  }
  /* Miniatyren dras ut till kortets kanter — samma bildfält som gamla kortet,
     men utan dess 9-14px hörn. */
  .tumme {
    display: block;
    width: auto;
    margin: -14px -15px 4px;
    aspect-ratio: 16 / 9;
    object-fit: cover;
    background: var(--sunken);
    border-bottom: 1px solid var(--line);
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
    font-size: 0.72rem;
    font-weight: 500;
    border-radius: 3px;
    padding: 2px 8px;
    margin: 2px 0 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
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
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 8px;
    padding-top: 10px;
    border-top: 1px solid var(--line);
  }
  /* Identisk med .ghost i frontend/src/lib/transkribera/Korning.svelte:284-293. */
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 9px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  /* Raderingen är den enda destruktiva knappen på kortet — den bär färgen,
     inte en egen form. */
  .fara { color: var(--bad); }
</style>
