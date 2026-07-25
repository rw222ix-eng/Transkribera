<script>
  // Språkparet och den automatiskt valda modellen. Speglar app.js:4504-4532.
  import { tr } from './stores.svelte.js';
  import { pickLang, pickTargetLang } from './actions.js';
  import { katalog, modellNamn, fitDot } from './katalog.svelte.js';

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
  // för det språk som redan står i formuläret. Speglar loadModels patch.model
  // (app.js:3020-3024).
  $effect(() => {
    if (katalog.klar && !tr.model) pickLang(/** @type {'sv'|'en'} */ (tr.language));
  });
</script>

<div class="ruta">
  <p class="label">Språk</p>

  <div class="par">
    <div class="halva">
      <span class="rubrik">Talat språk</span>
      <div class="seg" role="group" aria-label="Talat språk">
        {#each SPRAK as [kod, etikett]}
          <button
            type="button"
            aria-pressed={tr.language === kod}
            onclick={() => pickLang(kod)}
          >{etikett}</button>
        {/each}
      </div>
    </div>

    <span class="pil" aria-hidden="true">→</span>

    <div class="halva">
      <span class="rubrik">Resultatspråk</span>
      <div class="seg" role="group" aria-label="Resultatspråk">
        {#each SPRAK as [kod, etikett]}
          <button
            type="button"
            aria-pressed={tr.targetLanguage === kod}
            onclick={() => pickTargetLang(kod)}
          >{etikett}</button>
        {/each}
      </div>
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
  .seg {
    display: flex;
    gap: 3px;
    padding: 3px;
    background: var(--track);
    border: 1px solid var(--line);
    border-radius: 5px;
  }
  .seg button {
    flex: 1 1 0;
    border: none;
    border-radius: 3px;
    padding: 8px 14px;
    background: transparent;
    color: var(--ink-2);
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .seg button[aria-pressed='true'] { background: var(--surface); color: var(--ink); }
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
