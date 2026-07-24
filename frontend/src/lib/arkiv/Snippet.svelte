<script>
  let { text = '' } = $props();

  // Servern markerar träffar med styrtecknen \x02 (start) och \x03 (slut) —
  // samma kontrakt som /api/search. Texten före första \x02 är aldrig en träff;
  // därefter är biten fram till \x03 träffen och resten vanlig text.
  const START = '\x02';
  const END = '\x03';

  const parts = $derived.by(() => {
    const out = [];
    const chunks = text.split(START);
    // Text före första \x02 (och en marker utan avslutande \x03) är aldrig
    // en träff — men kan ändå råka innehålla ett löst \x03 om servern skickat
    // trasig markering. Sådana ska aldrig läcka som råa styrtecken i DOM:en.
    out.push({ hit: false, s: (chunks[0] ?? '').split(END).join('') });
    for (const chunk of chunks.slice(1)) {
      const cut = chunk.indexOf(END);
      if (cut < 0) {
        out.push({ hit: true, s: chunk.split(END).join('') });
      } else {
        out.push({ hit: true, s: chunk.slice(0, cut) });
        out.push({ hit: false, s: chunk.slice(cut + 1) });
      }
    }
    return out.filter((x) => x.s !== '');
  });
</script>

<p class="snippet">
  {#each parts as p}{#if p.hit}<mark>{p.s}</mark>{:else}{p.s}{/if}{/each}
</p>

<style>
  .snippet {
    margin: 6px 0 0;
    color: var(--ink-2);
  }
  mark {
    background: var(--accent-weak);
    color: var(--accent);
    border-radius: 2px;
    padding: 0 2px;
  }
</style>
