<script>
  // Utdataformat och andra passet mot ljudet. Speglar app.js:4534-4552.
  // loadAudioModel() hämtas i TranskriberaView:s mount-effekt, inte här —
  // den här komponenten monteras och avmonteras med tr.step (varje "Lägg
  // till fler" ↔ "Nästa"), så ett eget $effect skulle hämta om statusen vid
  // varje stegväxling i stället för en gång per session.
  import { tr } from './stores.svelte.js';
  import { toggleFormat, toggleAudioCorrect, downloadAudioModel } from './actions.js';
  import Segment from '../Segment.svelte';

  // Etiketten versaliseras HÄR, i datan, inte med text-transform i CSS.
  // Segment.svelte delas med kontroller vars etiketter är vanlig svenska
  // ("Svenska", "Arbetsblad") — en versalregel i den komponenten hade
  // skrikit i alla utom den här. Versalerna är dessutom filändelsernas egen
  // form, inte en stilistisk effekt.
  const FORMAT = [
    ['srt', 'SRT'],
    ['txt', 'TXT'],
    ['vtt', 'VTT'],
  ];
</script>

<div class="rad">
  <span class="rubrik">Filformat</span>
  <!--
    FLERVAL — och det är hela poängen med att formen skiljer sig från
    språkvalets platta ovanför. Här går det att välja SRT *och* TXT; i
    Sprakval byter ett klick val. Se regeln överst i Segment.svelte.
  -->
  <Segment
    flerval
    alternativ={FORMAT}
    etikett="Filformat"
    arVald={(f) => !!tr.formats[f]}
    valj={toggleFormat}
  />
</div>

<div class="rad">
  <button
    type="button"
    class="switch"
    role="switch"
    aria-checked={tr.audioCorrect}
    aria-label="Rätta mot ljudet"
    onclick={toggleAudioCorrect}
  ><span class={['knopp', { pa: tr.audioCorrect }]}></span></button>
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
