<script>
  // Det strömmade svaret med sifferkällor. Speglar svarsstycket i
  // viewRecordings (app/web/static/app.js:4808-4819).
  import { sok } from './sok.svelte.js';
  import { parseCitat } from './citat.js';
  import { oppnaKalla, stallFoljdfraga } from './sokActions.js';
  import Kalenderforslag from './Kalenderforslag.svelte';

  // Enter skickar följdfrågan. preventDefault så fältet inte submittar den
  // dialog det ligger i närheten av.
  function foljdKey(e) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    stallFoljdfraga();
  }

  const klar = $derived(!sok.fragar && !!sok.svar);

  // Sifferkällorna byggs FÖRST när svaret är klart. Under strömningen kan en
  // halv "[1" annars blinka förbi som text.
  const citat = $derived(klar && sok.kallor.length ? parseCitat(sok.svar, sok.kallor.length) : null);

  // Källistan filtrerar bort en referens vars källa saknas i sok.kallor —
  // ett inkonsekvent svar från servern ska inte rendera en rad med tomt namn.
  const citerade = $derived(
    citat ? citat.refs.map((r) => ({ num: r.num, kalla: sok.kallor[r.kallIndex] })).filter((x) => x.kalla) : [],
  );

  // Rubriken räknar bara FAKTISKT CITERADE källor (app.js:3797-3807) — det som
  // visas ska vara det svaret verkligen lutar sig mot. Härledd ur citerade.length,
  // INTE citat.refs.length: det senare räknar även med referenser som filtret
  // ovan tog bort, vilket kan påstå fler källor i rubriken än listan visar.
  const antalCiterade = $derived(citerade.length);
  const rubrik = $derived(
    antalCiterade === 0
      ? 'Svar'
      : antalCiterade === 1
        ? 'Svar — 1 källa'
        : `Svar — ${antalCiterade} källor`,
  );

  const meta = (s) => [s.group, s.course, s.datum].filter(Boolean).join(' · ');
  // FYND 2 I SLUTGRANSKNINGEN: `s` kan vara undefined — `.cite`-spannet nedan
  // anropar namn(sok.kallor[t.kallIndex]) för VARJE citeringstoken, oavsett
  // om källan finns i sok.kallor. Anropsställena (`namn(...) || 'okänd'`) var
  // redan skrivna som om ett falsy returvärde vore möjligt, men ett oskyddat
  // s.name kastade FÖRE den punkten nåddes. Syskonderivatet `citerade` ovan
  // filtrerar uttryckligen bort just det fallet (`.filter((x) => x.kalla)`)
  // — samma skydd hör hemma här, inte bara där.
  const namn = (s) => (s ? [s.name, s.datum].filter(Boolean).join(' · ') : '');
</script>

{#if sok.fragaFel}
  <!--
    FELET HAR EN EGEN KANAL. Gamla appen renderar det SOM svaret
    (askAnswer = msg, app.js:1870), vilket gör ett fel omöjligt att skilja från
    ett kort svar. Ingen egen roll här — vyns enda annonserande nod är dess
    role="status", och ett andra fäller antalsspärren.
  -->
  <p class="fragafel">{sok.fragaFel}</p>
{:else if sok.svar}
  <section class="svar">
    <h2 class="rubrik">{rubrik}</h2>

    <!--
      REN TEXT med white-space: pre-wrap, ingen markdown och ingen KaTeX. Det
      är en MEDVETEN skillnad mot lektionschatten, som renderar rikt:
      arkivsvaret ska läsas som ett citatunderlag.
    -->
    <p class="text">
      {#if citat}
        {#each citat.tokens as t, i (i)}
          {#if t.text}{t.text}{:else}<button
              class="cite"
              onclick={() => oppnaKalla(sok.kallor[t.kallIndex])}
              title={namn(sok.kallor[t.kallIndex]) || `Källa ${t.cite}`}
              aria-label="Öppna källa {t.cite} — {namn(sok.kallor[t.kallIndex]) || 'okänd'}"
              >{t.cite}</button
            >{/if}
        {/each}
      {:else}{sok.svar}{/if}{#if sok.fragar}<span class="markor" aria-hidden="true"></span>{/if}
    </p>

    {#if citerade.length}
      <ul class="kallor">
        {#each citerade as c (c.num)}
          <li class="kalla">
            <span class="num">{c.num}</span>
            <span class="kallnamn">{c.kalla.name || '(namnlös)'}</span>
            {#if meta(c.kalla)}<span class="kallmeta">{meta(c.kalla)}</span>{/if}
          </li>
        {/each}
      </ul>
    {/if}

    <!--
      KALENDERFÖRSLAGET ligger mellan svaret och följdfrågorna: det är en
      följd av svaret, och en följdfråga gäller ofta just förslaget.
    -->
    <Kalenderforslag />

    <!--
      FÖLJDFRÅGORNA LIGGER INLINE, inte i en zoom-modal. Gamla appen visar dem
      bara i ett helskärmsläge (askZoom) och utanför det bara en återvändsgränd
      ("N följdfrågor — öppna chattvyn för att fortsätta"). Inline är färre
      rörliga delar och närmare den lugna riktningen i DESIGN.md.

      INGET SAMTALSMINNE: varje följdfråga är en fristående arkivsökning — se
      kommentaren i sok.svelte.js.
    -->
    {#if klar}
      <div class="foljd">
        {#each sok.foljdfragor as f, i (i)}
          <p class="fraga">{f.q}</p>
          <p class="foljdsvar">
            {f.a}{#if f.skriver}<span class="markor" aria-hidden="true"></span>{/if}
          </p>
        {/each}

        <div class="foljdfalt">
          <input
            class="foljdinput"
            bind:value={sok.foljdInput}
            onkeydown={foljdKey}
            aria-label="Ställ en följdfråga"
            placeholder="Ställ en följdfråga …"
          />
          <button class="ghost" onclick={stallFoljdfraga} disabled={sok.foljdSkriver}>
            {sok.foljdSkriver ? 'Söker …' : 'Skicka'}
          </button>
        </div>
      </div>
    {/if}
  </section>
{/if}

<style>
  .svar {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 16px 18px;
    margin-top: 14px;
  }
  .rubrik {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--ink);
    margin: 0 0 10px;
  }
  .text {
    font-size: 1.03rem;
    line-height: 1.75;
    color: var(--ink);
    white-space: pre-wrap;
    max-width: 62ch;
    margin: 0;
    overflow-wrap: anywhere;
  }

  /* Sifferkällan är nu en KNAPP — den öppnar källmodalen. Fram till B3c var
     den ett rollöst <span> med role="img", eftersom en knapp som inte gör
     något är värre än ingen knapp. Nu gör den något, och då är <button> rätt
     element: det ger tangentbordsfokus, Enter/Space och en roll som bär det
     tillgängliga namnet utan att behöva role-attributet. */
  .cite {
    display: inline-block;
    min-width: 15px;
    text-align: center;
    background: var(--accent-weak);
    color: var(--accent);
    border: 0;
    border-radius: 2px;
    padding: 0 4px;
    margin: 0 1px;
    font-family: inherit;
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    vertical-align: 1px;
    cursor: pointer;
  }
  .cite:hover { background: var(--accent); color: var(--on-accent); }

  .markor {
    display: inline-block;
    width: 2px;
    height: 1em;
    background: var(--accent);
    vertical-align: -2px;
    margin-left: 3px;
  }

  .kallor {
    list-style: none;
    margin: 16px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .kalla {
    display: flex;
    align-items: baseline;
    gap: 9px;
    flex-wrap: wrap;
  }
  .num {
    flex: none;
    min-width: 15px;
    text-align: center;
    background: var(--accent-weak);
    color: var(--accent);
    border-radius: 2px;
    padding: 0 4px;
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
  }
  .kallnamn {
    font-size: 1.03rem;
    color: var(--ink);
    overflow-wrap: anywhere;
  }
  .kallmeta {
    font-size: 0.72rem;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }

  /* FÖLJDFRÅGORNA. Hårlinje över, inte ett eget kort: de hör till svaret
     ovanför, inte bredvid det. */
  .foljd {
    margin-top: 18px;
    padding-top: 14px;
    border-top: 1px solid var(--line);
  }
  /* Frågan högerställd, svaret vänsterställt — samma läsriktning som gamla
     appens chattbubblor, men utan bubblorna. */
  .fraga {
    font-size: 1.03rem;
    color: var(--ink-2);
    margin: 0 0 4px;
    text-align: right;
    max-width: 62ch;
    margin-left: auto;
    overflow-wrap: anywhere;
  }
  .foljdsvar {
    font-size: 1.03rem;
    line-height: 1.75;
    color: var(--ink);
    white-space: pre-wrap;
    max-width: 62ch;
    margin: 0 0 16px;
    overflow-wrap: anywhere;
  }

  .foljdfalt {
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--surface);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 4px 4px 4px 12px;
  }
  .foljdfalt:focus-within { border-color: var(--accent); }
  .foljdinput {
    flex: 1;
    min-width: 0;
    background: transparent;
    border: 0;
    color: var(--ink);
    font-family: inherit;
    font-size: 1.03rem;
    padding: 8px 0;
  }
  .foljdinput::placeholder { color: var(--ink-3); }

  /* Identisk med .ghost i InspelningarView.svelte, som i sin tur är kopian av
     Korning.svelte:284-293. */
  .ghost {
    flex: none;
    background: transparent;
    color: var(--ink-2);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 8px 16px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .ghost:hover:not(:disabled) { border-color: var(--ink); color: var(--ink); }
  .ghost:disabled { cursor: default; opacity: 0.6; }

  /* Felet bär samma typform som tomtillstånden i vyn — löpande text, ingen ram,
     ingen ikon. Ett fel är inget larm. */
  .fragafel {
    font-size: 1.03rem;
    color: var(--ink-2);
    max-width: 52ch;
    margin: 18px 0 0;
  }
</style>
