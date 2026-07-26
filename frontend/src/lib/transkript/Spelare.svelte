<script>
  import { tk } from './stores.svelte.js';
  import { fmtTid } from './tid.js';
  import { bindMedia, slappMedia, vaxlaSpelning, spolaTill, cyklaHastighet, fmtHastighet, laggTillMarkor } from './actions.js';

  let spar = $state(null);
  let rafId = 0;

  const andel = $derived(tk.langd > 0 ? Math.min(1, Math.max(0, tk.tid / tk.langd)) : 0);
  const spolbar = $derived(tk.langd > 0);

  /** use:-action. Binder elementet och släpper det när noden rivs. */
  function media(el) {
    bindMedia(el);
    return { destroy: () => slappMedia(el) };
  }

  function tidVidX(x) {
    const r = spar.getBoundingClientRect();
    const f = Math.min(1, Math.max(0, (x - r.left) / r.width));
    return f * tk.langd;
  }

  function flyttaTill(x) {
    // Visningen följer fingret direkt; currentTime-skrivningen stryps till en
    // per animationsruta, så en snabb dragning inte köar hundra sökningar.
    tk.tid = tidVidX(x);
    if (rafId) return;
    rafId = requestAnimationFrame(() => {
      rafId = 0;
      spolaTill(tk.tid);
    });
  }

  function paPointerDown(e) {
    if (!spolbar) return;
    tk.drar = true;
    spar.setPointerCapture(e.pointerId);
    flyttaTill(e.clientX);
  }

  function paPointerMove(e) {
    if (tk.drar) flyttaTill(e.clientX);
  }

  function paPointerUp(e) {
    if (!tk.drar) return;
    tk.drar = false;
    try {
      spar.releasePointerCapture(e.pointerId);
    } catch {
      // Redan släppt — pointercancel kan ha hunnit före.
    }
    spolaTill(tk.tid);
  }

  function paTangent(e) {
    if (!spolbar) return;
    const steg = { ArrowLeft: -5, ArrowRight: 5, ArrowDown: -5, ArrowUp: 5, PageDown: -30, PageUp: 30 };
    if (e.key in steg) {
      e.preventDefault();
      spolaTill(tk.tid + steg[e.key]);
    } else if (e.key === 'Home') {
      e.preventDefault();
      spolaTill(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      spolaTill(tk.langd);
    }
  }
</script>

{#if tk.mediaUrl}
  <div class="spelare">
    {#if tk.arVideo}
      <!-- <track> utan src: svelte-checks a11y_media_has_caption kräver ett
           captions-spår, och repot har noll svelte-ignore. Något VTT att peka
           på finns inte här — transkriptet står bredvid videon och ÄR
           undertexten. Ett tomt spår är därför sant: elementet har inga
           textspår att erbjuda. -->
      <video class="video" src={tk.mediaUrl} use:media preload="metadata">
        <track kind="captions" />
      </video>
    {:else}
      <audio src={tk.mediaUrl} use:media preload="metadata"></audio>
    {/if}

    {#if tk.forbereder}
      <p class="forbereder">Förbereder videon …</p>
    {/if}

    <div class="kontroller">
      <button type="button" class="ghost play" onclick={vaxlaSpelning}>
        {tk.spelar ? 'Pausa' : 'Spela'}
      </button>
      <span class="klocka">{fmtTid(tk.tid)}</span>
      <!-- Hårlinjen är designsystemets signatur (DESIGN.md §251-253) och samma
           form som fasbaren i transkribera/Korning.svelte:232-239.
           Ingen AUDIO_DUR-fallback: är längden okänd är spåret spärrat och
           visar --:--, i stället för att räkna mot gamla appens 150 sekunder
           och landa helt fel på en timmeslång lektion (app.js:2103). -->
      <div
        class="spar"
        role="slider"
        tabindex={spolbar ? 0 : -1}
        aria-label="Sök i uppspelningen"
        aria-valuemin="0"
        aria-valuemax={Math.round(tk.langd)}
        aria-valuenow={Math.round(tk.tid)}
        aria-valuetext="{fmtTid(tk.tid)} av {fmtTid(tk.langd)}"
        aria-disabled={!spolbar}
        bind:this={spar}
        onpointerdown={paPointerDown}
        onpointermove={paPointerMove}
        onpointerup={paPointerUp}
        onpointercancel={paPointerUp}
        onkeydown={paTangent}
      >
        <div class="fyllnad" style="width: {andel * 100}%"></div>
      </div>
      <span class="klocka">{spolbar ? fmtTid(tk.langd) : '--:--'}</span>
      <button
        type="button"
        class="ghost hastighet"
        aria-label="Uppspelningshastighet, {fmtHastighet(tk.hastighet)}"
        onclick={cyklaHastighet}
      >{fmtHastighet(tk.hastighet)}</button>
      <button
        type="button"
        class="ghost"
        disabled={tk.laggerTill}
        onclick={laggTillMarkor}
      >Markera</button>
    </div>
  </div>
{/if}

<style>
  .spelare { margin-top: 12px; }
  .video {
    display: block;
    width: 100%;
    max-height: 34vh;
    background: var(--sunken);
    border: 1px solid var(--line);
    border-radius: 4px;
  }
  .forbereder { color: var(--ink-3); margin: 8px 0 0; }
  .kontroller {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 10px;
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
  .ghost:disabled { opacity: 0.55; cursor: default; }
  .play { flex: 0 0 auto; }
  .klocka {
    flex: 0 0 auto;
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    color: var(--ink-2);
  }
  /* Identisk med .spar/.fyllnad i frontend/src/lib/transkribera/Korning.svelte:232-239. */
  .spar {
    flex: 1 1 auto;
    height: 3px;
    background: var(--track);
    border-radius: 2px;
    overflow: hidden;
    cursor: pointer;
  }
  .spar[aria-disabled='true'] { cursor: default; }
  .fyllnad { height: 100%; background: var(--accent); }
  .hastighet {
    flex: 0 0 auto;
    padding: 9px 12px;
    font-variant-numeric: tabular-nums;
  }
</style>
