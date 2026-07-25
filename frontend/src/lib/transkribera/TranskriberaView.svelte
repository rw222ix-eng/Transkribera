<script>
  // Transkriberingsguiden, steg 1 — Källa. Speglar viewTranscribe:s
  // stepSource-gren (app/web/static/app.js:4383-4470), omstylad till
  // designsystemet. Steg 2 kom i plan A2. Steg 3 kommer i plan A3.
  import { tr } from './stores.svelte.js';
  import { addSample, addSampleCorrupt, goConfig, loadAudioModel } from './actions.js';
  import Stegindikator from './Stegindikator.svelte';
  import Dropzone from './Dropzone.svelte';
  import LankFalt from './LankFalt.svelte';
  import Kolista from './Kolista.svelte';
  import Installningar from './Installningar.svelte';
  import Korning from './Korning.svelte';
  import { loadKatalog } from './katalog.svelte.js';

  // Katalogen och ljudmodellens status hämtas en gång när vyn monteras —
  // skalet håller vyn monterad hela sessionen, så det här körs inte om vid
  // flikbyten eller stegväxlingar. Ett fel i katalogen (offline eller
  // trasig hårdvaruskanning, se app/gpu_arbiter.py) skulle annars lämna
  // CTA:n i Installningar.svelte fastnad på "Laddar modeller …" utan
  // förklaring.
  $effect(() => {
    loadKatalog().then((ok) => {
      if (ok === false) {
        tr.fileNoteArt = 'fel';
        tr.fileError = 'Kunde inte läsa modellistan — starta om appen och försök igen.';
      }
    });
    loadAudioModel();
  });
</script>

<section class="view">
  <Stegindikator />

  <!--
    En enda hoistad live-region bär texten för skärmläsare, oavsett vilket
    steg läraren står på — annars hinner ett fel som skrivs medan hon står på
    steg 2 (t.ex. downloadAudioModel i actions.js) aldrig annonseras. Noden
    är permanent i DOM:en (aldrig {#if}) och bara VISUELLT gömd med en
    klippande teknik — INTE display:none, som tar bort den ur
    tillgänglighetsträdet och gör att role="status" inte längre kan
    annonsera mutationen (plan A2-fixrunda, punkt 1).
    Varje steg renderar därutöver sin egen SYNLIGA kopia av samma text, nära
    fältet den gäller, markerad aria-hidden="true" — bara live-regionen ovan
    ska annonseras, inte båda.
  -->
  <p class="fel-sr" role="status">{tr.fileError}</p>

  {#if tr.step === 'source'}
    <p class="eyebrow">STEG 1 — KÄLLA</p>
    <h1 class="display">Vad vill du <span class="ser">transkribera?</span></h1>
    <p class="lede">
      Dra in en eller flera filer, eller välj från datorn — allt körs på din egen dator.
    </p>

    <Dropzone />
    <LankFalt />

    <p class="prova">
      Eller prova med
      <button type="button" class="lank" onclick={addSample}>ett exempel</button>
      <button type="button" class="lank" onclick={addSampleCorrupt}>skadad_inspelning.m4a</button>
    </p>

    <!--
      Synlig kopia av live-regionen ovan, i den position raden hade före
      hoisten till plan A2-fixrunda: direkt under källfälten. Riktig textnod,
      INTE CSS-genererat innehåll (content: attr(...)) — det gick inte att
      markera, kopiera eller Ctrl+F-söka, och skulle försvinna helt spårlöst
      om stilmallen någonsin saknades vid paketering. Raden är redan
      aria-hidden så skärmläsare struntar i den; det är live-regionen ovan
      som annonseras. e2e-testerna skiljer den här synliga kopian från
      live-regionen via data-testid="statusrad" i stället för att leta upp
      texten två gånger (se e2e/transkribera-kalla.spec.mjs).
    -->
    <p class="fel" class:info={tr.fileNoteArt === 'info'} aria-hidden="true" data-testid="statusrad">{tr.fileError}</p>

    {#if tr.queue.length}
      <div class="ko-wrap">
        <Kolista />
      </div>
      <p class="antal">{tr.queue.length} {tr.queue.length === 1 ? 'fil' : 'filer'} i kön.</p>
    {/if}

    <p class="vidare">
      <button
        type="button"
        class="primar"
        disabled={!tr.queue.length}
        onclick={goConfig}
      >Nästa: inställningar</button>
    </p>
  {:else if tr.step === 'config'}
    <Installningar />
  {:else}
    <Korning />
  {/if}
</section>

<style>
  .view { max-width: 860px; margin: 0 auto; padding: 56px 24px 96px; }
  .eyebrow {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
    margin: 0 0 14px;
  }
  .display {
    font-family: var(--sans);
    font-weight: 700;
    font-size: 1.5rem;
    line-height: 1.15;
    letter-spacing: -0.02em;
    color: var(--ink);
    margin: 0 0 10px;
  }
  .display .ser {
    font-family: var(--serif);
    font-style: italic;
    font-weight: 400;
    font-size: 2.375rem;
    line-height: 1.05;
    letter-spacing: -0.01em;
  }
  .lede { max-width: 62ch; color: var(--ink-2); margin: 0; }
  .prova { color: var(--ink-3); margin: 20px 0 0; display: flex; gap: 12px; flex-wrap: wrap; }
  .lank {
    border: none;
    background: transparent;
    color: var(--ink-2);
    font-family: inherit;
    font-size: inherit;
    padding: 0;
    cursor: pointer;
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .lank:hover { color: var(--ink); }
  .fel { color: var(--bad); margin: 14px 0 0; }
  .fel:empty { display: none; }
  .fel.info { color: var(--ink-3); }
  /* Klippande teknik — noden finns kvar i tillgänglighetsträdet men upptar
     ingen synlig plats, till skillnad från display:none. */
  .fel-sr {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  .ko-wrap { margin: 20px 0 0; }
  .antal { color: var(--ink-3); margin: 10px 0 0; }
  .vidare { margin: 24px 0 0; }
  .primar {
    background: var(--btn-bg);
    color: var(--btn-fg);
    border: none;
    border-radius: 4px;
    padding: 12px 22px;
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .primar:disabled { opacity: 0.55; cursor: default; }
</style>
