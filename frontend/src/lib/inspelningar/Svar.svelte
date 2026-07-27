<script>
  // Det strömmade svaret med sifferkällor. Speglar svarsstycket i
  // viewRecordings (app/web/static/app.js:4808-4819).
  import { sok } from './sok.svelte.js';
  import { parseCitat } from './citat.js';

  const klar = $derived(!sok.fragar && !!sok.svar);

  // Sifferkällorna byggs FÖRST när svaret är klart. Under strömningen kan en
  // halv "[1" annars blinka förbi som text.
  const citat = $derived(klar && sok.kallor.length ? parseCitat(sok.svar, sok.kallor.length) : null);

  // Rubriken räknar bara FAKTISKT CITERADE källor (app.js:3797-3807) — det som
  // visas ska vara det svaret verkligen lutar sig mot.
  const antalCiterade = $derived(citat ? citat.refs.length : 0);
  const rubrik = $derived(
    antalCiterade === 0
      ? 'Svar'
      : antalCiterade === 1
        ? 'Svar — 1 källa'
        : `Svar — ${antalCiterade} källor`,
  );

  const citerade = $derived(
    citat ? citat.refs.map((r) => ({ num: r.num, kalla: sok.kallor[r.kallIndex] })).filter((x) => x.kalla) : [],
  );

  const meta = (s) => [s.group, s.course, s.datum].filter(Boolean).join(' · ');
  const namn = (s) => [s.name, s.datum].filter(Boolean).join(' · ');
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
          {#if t.text}{t.text}{:else}<span
              class="cite"
              title={namn(sok.kallor[t.kallIndex]) || `Källa ${t.cite}`}
              aria-label="Källa {t.cite} — {namn(sok.kallor[t.kallIndex]) || 'okänd'}"
              >{t.cite}</span
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
      <!--
        Vad B3b INTE gör, utskrivet i stället för antytt. Samma hållning som B1
        och B3a: säg var läraren kan gå, navigera inte till en platshållare.
        Källmodalen är B3c.
      -->
      <p class="senare">
        Att öppna en källa i transkriptet migreras i en senare plan. Tills dess
        finns det i den gamla appen.
      </p>
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

  /* Sifferkällan är en MARKÖR, inte en knapp — att öppna källan är B3c. Ett
     <span> utan tabindex är rätt: en knapp som inte gör något är värre än
     ingen knapp. */
  .cite {
    display: inline-block;
    min-width: 15px;
    text-align: center;
    background: var(--accent-weak);
    color: var(--accent);
    border-radius: 2px;
    padding: 0 4px;
    margin: 0 1px;
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    vertical-align: 1px;
  }

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

  .senare {
    font-size: 0.72rem;
    color: var(--ink-3);
    max-width: 52ch;
    margin: 16px 0 0;
  }

  /* Felet bär samma typform som tomtillstånden i vyn — löpande text, ingen ram,
     ingen ikon. Ett fel är inget larm. */
  .fragafel {
    font-size: 1.03rem;
    color: var(--ink-2);
    max-width: 52ch;
    margin: 18px 0 0;
  }
</style>
