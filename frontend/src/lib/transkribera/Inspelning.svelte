<script>
  // Inspelningswidgeten i guidens steg 1. Speglar app.js:4424-4444 funktionellt,
  // men omstylad: gamla widgeten är ren inline-CSS med 8-12px hörn, vilket
  // DESIGN.md avvisar. Ingen literal hex, bara tokens.
  import { tr } from './stores.svelte.js';
  import { startRecording, stopRecording, cancelRecording, recSupported } from './inspelning.svelte.js';

  const stods = recSupported();

  const tid = $derived.by(() => {
    const n = Math.max(0, Math.floor(tr.recElapsed || 0));
    return `${String(Math.floor(n / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}`;
  });
</script>

<div class="rad">
  <span class="etikett">ELLER SPELA IN</span>

  <div class="ruta" class:kor={tr.recording}>
    {#if tr.recording}
      <span class="prick" aria-hidden="true"></span>
      <span class="text">Spelar in</span>
      <span class="tid">{tid}</span>
      <div class="matare" title="Mikrofonnivå">
        <div class="fyllnad" class:tyst={tr.recSilent} style:transform={`scaleX(${tr.recLevel})`}></div>
      </div>
      {#if tr.recSilent}<span class="ingen">Ingen signal?</span>{/if}
      <span class="spacer"></span>
      <button type="button" class="ghost" onclick={cancelRecording}>Avbryt</button>
      <button type="button" class="primar" onclick={stopRecording}>Stoppa och lägg till</button>
    {:else}
      <span class="text" class:av={!stods}>
        {stods
          ? 'Spela in lektionen direkt — ljudet sparas lokalt'
          : 'Inspelning kräver mikrofonåtkomst i webbläsaren'}
      </span>
      <span class="spacer"></span>
      <button type="button" class="primar" disabled={!stods} onclick={startRecording}>
        Starta inspelning
      </button>
    {/if}
  </div>
</div>

{#if tr.recError}
  <p class="rec-fel" role="status">{tr.recError}</p>
{/if}

<style>
  .rad { margin: 20px 0 0; }
  /* Mikroetiketten är den ENDA platsen mono får stå på i widgeten — versal,
     kort, en rubrik för raden under. DESIGN.md reserverar var(--mono) för
     just det; tider, meningar och knapptexter går i sans. */
  .etikett {
    display: block;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
    margin: 0 0 10px;
  }
  .ruta {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 14px 16px;
  }
  /* Pågående inspelning markeras med en tydligare kant, inte med en färgad
     yta — panelen ska förbli papper, inte bli en larmruta. */
  .ruta.kor { border-color: var(--line-2); }
  /* 8px bred, 4px radie = en exakt cirkel, och håller sig inom 2-5px-regeln. */
  .prick {
    width: 8px;
    height: 8px;
    border-radius: 4px;
    background: var(--bad);
    flex: none;
    animation: pulsera 1.6s ease-in-out infinite;
  }
  /* Komponent-scopad — gamla appens globala `pulse` i style.css hör till den
     gamla appen och får inte dupliceras hit. */
  @keyframes pulsera {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.35; }
  }
  @media (prefers-reduced-motion: reduce) {
    .prick { animation: none; }
  }
  .text { color: var(--ink-2); font-size: 1.03rem; }
  .text.av { color: var(--ink-3); }
  .tid { color: var(--ink); font-size: 1.03rem; font-variant-numeric: tabular-nums; }
  .matare {
    width: 96px;
    height: 3px;
    background: var(--track);
    border-radius: 2px;
    overflow: hidden;
    flex: none;
  }
  /* scaleX sätts inline ur tr.recLevel (0-1). transform-origin måste vara
     vänsterkanten, annars växer stapeln åt båda hållen från mitten. */
  .fyllnad {
    height: 100%;
    background: var(--ok);
    transform: scaleX(0);
    transform-origin: left center;
  }
  .fyllnad.tyst { background: var(--bad); }
  .ingen { color: var(--bad); font-size: 1.03rem; }
  .spacer { flex: 1; }
  /* Samma knapputseende som Korning.svelte och Installningar.svelte — widgeten
     uppfinner inga egna knappklasser. */
  .primar {
    background: var(--btn-bg);
    color: var(--btn-fg);
    border: none;
    border-radius: 4px;
    padding: 10px 20px;
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .primar:disabled { opacity: 0.55; cursor: default; }
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
  /* Inspelningens fel bär en EGEN rad, inte guidens delade tr.fileError —
     ett mikrofonfel hör inte hemma i samma statusrad som filformatsfel. */
  .rec-fel { color: var(--bad); margin: 12px 0 0; }
</style>
