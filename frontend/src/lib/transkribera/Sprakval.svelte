<script>
  // Språkparet och den automatiskt valda modellen. Speglar app.js:4504-4532.
  import { tr } from './stores.svelte.js';
  import { pickLang, pickTargetLang, syncModel } from './actions.js';
  import { katalog, modellNamn, fitDot } from './katalog.svelte.js';
  import Segment from '../Segment.svelte';

  /** @type {Array<['sv'|'en', string]>} */
  const SPRAK = [['sv', 'Svenska'], ['en', 'Engelska']];

  const oversatter = $derived(
    !!(tr.targetLanguage && tr.language && tr.targetLanguage !== tr.language),
  );
  const namn = (c) => (c === 'en' ? 'engelska' : 'svenska');
  const hint = $derived(
    oversatter
      ? 'Översätts från ' + namn(tr.language) + ' till ' + namn(tr.targetLanguage) + '.'
      : 'Resultatet blir på ' + namn(tr.targetLanguage || tr.language) + ' — samma som det talade språket.',
  );
  const modellRad = $derived(
    tr.model
      ? modellNamn(tr.model) + ' · väljs automatiskt'
      : 'Ingen modell för ' + namn(tr.language) + ' · ingen modell installerad för språket',
  );
  const prick = $derived(tr.model ? fitDot(tr.model) : 'var(--bad)');

  // Katalogen kommer efter första renderingen; när den landar väljs modellen
  // för det språk som redan står i formuläret. Bara modellen — ett
  // resultatspråk läraren redan valt får inte nollställas. Speglar
  // loadModels patch.model (app.js:3020-3024).
  $effect(() => {
    if (katalog.klar && !tr.model) syncModel();
  });
</script>

<div class="ruta">
  <p class="label">Språk</p>

  <div class="par">
    <div class="halva">
      <span class="rubrik">Talat språk</span>
      <Segment
        alternativ={SPRAK}
        etikett="Talat språk"
        arVald={(kod) => tr.language === kod}
        valj={pickLang}
      />
    </div>

    <span class="pil" aria-hidden="true">→</span>

    <div class="halva">
      <span class="rubrik">Resultatspråk</span>
      <Segment
        alternativ={SPRAK}
        etikett="Resultatspråk"
        arVald={(kod) => tr.targetLanguage === kod}
        valj={pickTargetLang}
      />
    </div>
  </div>

  <p class="fot">
    <span class="prick" style:background={prick} aria-hidden="true"></span>
    <span>{modellRad}</span>
    <span class="hint">{hint}</span>
  </p>
</div>

<style>
  .ruta {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 18px 20px;
    margin-top: 28px;
  }
  .label {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin: 0 0 16px;
  }
  .par { display: flex; align-items: flex-end; gap: 16px; flex-wrap: wrap; }
  .halva { flex: 1 1 0; min-width: 180px; display: flex; flex-direction: column; gap: 8px; }
  .rubrik { color: var(--ink-2); }
  .pil { color: var(--ink-3); padding-bottom: 9px; }
  /* Segmenten delar bredd lika inom språkparet, så de två halvorna blir
     spegelbilder. Formen i övrigt bor i Segment.svelte; det här är den enda
     lokala avvikelsen och den hör till LAYOUTEN här, inte till kontrollen. */
  .halva :global(.seg button) { flex: 1 1 0; }
  .fot {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
    margin: 16px 0 0;
    padding-top: 14px;
    border-top: 1px solid var(--line);
    color: var(--ink-2);
  }
  .prick {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex: 0 0 auto;
    align-self: center;
  }
  .hint { margin-left: auto; color: var(--ink-3); }
</style>
