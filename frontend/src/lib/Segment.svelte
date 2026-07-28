<script>
  /*
    Appens segmentkontroll. Ersätter fyra egna implementationer som gjorde
    samma sak med fyra olika utseenden (Sprakval, BuildPanel:s typval,
    Sokfalt:s lägen, ArkivSearch:s lägen) plus Formatval:s chips.

    REGELN KOMPONENTEN KODAR IN — och hela skälet till att den finns:

        ENVAL  → PLATTA  (segmenten ligger på en --track-platta, det valda
                          lyfts upp på --surface)
        FLERVAL → CHIPS  (fristående, hårlinjeramade; valda bär --accent-weak)

    Före det här bar Sokfalt:s LÄGEN (enval: Fråga AI *eller* Sök ord) exakt
    samma fristående chipsform som Formatval:s FORMAT (flerval: SRT *och* TXT).
    Två motsatta kontrakt, ett utseende — läraren kunde inte se på en kontroll
    om ett klick byter val eller lägger till ett. Det är den ambiguiteten
    formvalet ovan finns för att ta bort, inte estetiken.

    aria-pressed behålls i BÅDA lägena. För flerval är det rätt per definition.
    För enval vore role="radiogroup"/aria-checked ARIA:s bokstav, men samtliga
    fem kontroller — och de e2e-specar som mäter dem — står redan på
    aria-pressed, och en växling dit är en egen a11y-ändring med egen
    testrunda. Gruppen bär role="group" med aria-label, så kontrollen
    annonseras som en enhet oavsett.

    PILTANGENTER ingår för att en segmentkontroll som ser ut som en
    segmentkontroll också ska bete sig som en: ←/→ (och ↑/↓) flyttar fokus
    mellan segmenten, Home/End till första/sista. Utan dem kräver varje
    segment ett eget tabbstopp, vilket är den vanligaste anledningen till att
    tangentbordsanvändare tabbar förbi hela kontrollen.

    Fokus FLYTTAS bara — valet följer inte med. Att låta piltangenten välja
    (ARIA:s "automatic activation") är rätt för flikar, men här kostar varje
    val något: Sokfalt nollställer träfflistan vid lägesbyte, och BuildPanel
    byter hela formuläret. Att svepa förbi ett segment ska inte göra det.
  */

  let {
    /** @type {Array<[string, string]>} [värde, etikett] */
    alternativ,
    /** aria-label för gruppen. Obligatorisk — en namnlös grupp är osynlig
        i en skärmläsares elementlista. */
    etikett,
    /** @type {(v: string) => boolean} */
    arVald,
    /** @type {(v: string) => void} */
    valj,
    /** Flerval ritar chips i stället för platta. Se regeln överst. */
    flerval = false,
  } = $props();

  // Lyssnaren sitter på KNAPPARNA, inte på gruppen. En <div role="group"> med
  // onkeydown är en icke-interaktiv nod med tangentbordshantering, vilket
  // svelte-check fäller (a11y_no_noninteractive_element_interactions) — och
  // med rätta: händelsen hör hemma där fokus faktiskt kan stå.
  function tangent(e) {
    const steg =
      e.key === 'ArrowRight' || e.key === 'ArrowDown'
        ? 1
        : e.key === 'ArrowLeft' || e.key === 'ArrowUp'
          ? -1
          : 0;
    if (!steg && e.key !== 'Home' && e.key !== 'End') return;

    const knappar = [...e.currentTarget.parentElement.querySelectorAll('button')];
    const nu = knappar.indexOf(e.currentTarget);
    if (nu === -1) return;

    e.preventDefault();
    const till =
      e.key === 'Home'
        ? 0
        : e.key === 'End'
          ? knappar.length - 1
          : // Modulo med + length: -1 % 3 är -1 i JS, inte 2.
            (nu + steg + knappar.length) % knappar.length;
    knappar[till].focus();
  }
</script>

<div class={['seg', { flerval }]} role="group" aria-label={etikett}>
  {#each alternativ as [v, text] (v)}
    <button
      type="button"
      aria-pressed={arVald(v)}
      onclick={() => valj(v)}
      onkeydown={tangent}
    >{text}</button>
  {/each}
</div>

<style>
  /* ENVAL — plattan. Formen kommer ur Sprakval.svelte, som var den mest
     genomarbetade av de fyra varianterna. */
  /* inline-flex, inte flex: som blockelement sträckte sig plattan över hela
     raden i Sokfalt och ArkivSearch och läste som ett verktygsfält i stället
     för en kontroll. Där kontrollen SKA fylla bredden (Sprakvals .halva) är
     föräldern en kolumn-flexbox, och där stretchar barnet ändå. */
  .seg {
    display: inline-flex;
    gap: 3px;
    padding: 3px;
    background: var(--track);
    border: 1px solid var(--line);
    border-radius: 5px;
  }
  .seg button {
    border: none;
    border-radius: 3px;
    padding: 8px 14px;
    background: transparent;
    color: var(--ink-2);
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    white-space: nowrap;
    cursor: pointer;
  }
  .seg button[aria-pressed='true'] {
    background: var(--surface);
    color: var(--ink);
  }

  /* FLERVAL — chipsen. Ingen platta, ingen gemensam ram: varje val står för
     sig, vilket är precis vad kontraktet säger. Formen kommer ur
     Formatval.svelte. */
  .seg.flerval {
    gap: 6px;
    padding: 0;
    background: transparent;
    border: none;
    border-radius: 0;
    flex-wrap: wrap;
  }
  .seg.flerval button {
    border: 1px solid var(--line);
    border-radius: 3px;
    padding: 7px 13px;
  }
  .seg.flerval button[aria-pressed='true'] {
    background: var(--accent-weak);
    color: var(--accent);
    border-color: var(--accent);
  }
</style>
