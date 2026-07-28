<script>
  // Släppytan plus den dolda filväljaren. Speglar app.js:4392-4398.
  import { tr } from './stores.svelte.js';
  import { openPicker, onPickFile, onDragOver, onDragLeave, onDrop, setFilInput } from './actions.js';

  let el = $state(null);
  $effect(() => {
    setFilInput(el);
    return () => setFilInput(null);
  });
</script>

<button
  type="button"
  class={['zon', { over: tr.dragging }]}
  onclick={openPicker}
  ondragover={onDragOver}
  ondragleave={onDragLeave}
  ondrop={onDrop}
>
  <span class="rubrik">Dra in filer — eller klicka för att välja</span>
  <span class="format">MP4 · MKV · MOV · MP3 · WAV · M4A — flera filer går bra</span>
</button>

<input
  bind:this={el}
  type="file"
  accept="audio/*,video/*"
  multiple
  onchange={onPickFile}
  hidden
/>

<style>
  .zon {
    display: flex;
    flex-direction: column;
    gap: 6px;
    width: 100%;
    margin-top: 24px;
    padding: 34px 24px;
    background: var(--surface);
    border: 1px dashed var(--line-2);
    border-radius: 5px;
    font-family: inherit;
    font-size: inherit;
    color: var(--ink);
    cursor: pointer;
    text-align: left;
  }
  .zon:hover, .zon.over { border-color: var(--accent); background: var(--accent-weak); }
  .rubrik { font-weight: 500; }
  .format { color: var(--ink-2); }
</style>
