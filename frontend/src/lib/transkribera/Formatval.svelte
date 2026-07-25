<script>
  // Utdataformat och andra passet mot ljudet. Speglar app.js:4534-4552.
  import { tr } from './stores.svelte.js';
  import { toggleFormat, toggleAudioCorrect, downloadAudioModel, loadAudioModel } from './actions.js';

  const FORMAT = ['srt', 'txt', 'vtt'];

  $effect(() => {
    loadAudioModel();
  });
</script>

<div class="rad">
  <span class="rubrik">Filformat</span>
  <div class="chips">
    {#each FORMAT as f}
      <button
        type="button"
        class="chip"
        aria-pressed={!!tr.formats[f]}
        onclick={() => toggleFormat(f)}
      >{f.toUpperCase()}</button>
    {/each}
  </div>
</div>

<div class="rad">
  <button
    type="button"
    class="switch"
    role="switch"
    aria-checked={tr.audioCorrect}
    aria-label="Rätta mot ljudet"
    onclick={toggleAudioCorrect}
  ><span class="knopp" class:pa={tr.audioCorrect}></span></button>
  <div class="text">
    <p class="titel">Rätta mot ljudet <span class="mjuk">· Gemma 4 (experimentell)</span></p>
    <p class="under">Ett andra pass som rättar transkriptet mot vad som faktiskt sägs.</p>
  </div>
  {#if !tr.audioModelInstalled}
    <button type="button" class="ghost" onclick={downloadAudioModel}>
      {tr.audioModelDownloading ? 'Laddar ner …' : 'Ladda ner modell'}
    </button>
  {/if}
</div>

<style>
  .rad {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 14px 18px;
    margin-top: 12px;
  }
  .rubrik { color: var(--ink-2); font-weight: 500; }
  .chips { display: flex; gap: 6px; }
  .chip {
    border: 1px solid var(--line);
    background: transparent;
    color: var(--ink-2);
    border-radius: 3px;
    padding: 7px 13px;
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .chip[aria-pressed='true'] {
    background: var(--accent-weak);
    color: var(--accent);
    border-color: var(--accent);
  }
  .switch {
    flex: 0 0 auto;
    width: 40px;
    height: 22px;
    border-radius: 5px;
    border: 1px solid var(--line-2);
    background: var(--track);
    padding: 2px;
    cursor: pointer;
  }
  .switch[aria-checked='true'] { background: var(--accent); border-color: var(--accent); }
  .knopp {
    display: block;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--knob);
    transition: transform 0.14s;
  }
  .knopp.pa { transform: translateX(18px); }
  .text { flex: 1; min-width: 200px; }
  .titel { margin: 0; color: var(--ink); font-weight: 500; }
  .mjuk { color: var(--ink-3); font-size: 0.72rem; }
  .under { margin: 2px 0 0; color: var(--ink-2); }
  .ghost {
    flex: 0 0 auto;
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 7px 14px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
</style>
