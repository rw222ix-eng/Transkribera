<script>
  // Terminstrender. Speglar trendsPanel (app/web/static/app.js:4958-4998).
  //
  // Gamla panelen visar fem 22px-siffror i egna --sunken-rutor. Det är exakt de
  // "hero-metric tiles" DESIGN.md avvisar, så räknarna blir i stället en
  // hårlinjeavgränsad rad med mikroetikett och 1.03rem-tal. Talen bär --sans
  // med tabular-nums, inte --mono: Mono-Is-Labels-Only.
  import { insp } from './stores.svelte.js';

  // Ordningen är klientens och skiljer sig från serverns dict-ordning. 'övrigt'
  // räknas av servern men visas MEDVETET inte — det är fallback-hinken och bär
  // ingen undervisningsmening (specens avsnitt 9).
  const RAKNARE = [
    { nyckel: 'svårighet', etikett: 'Svårigheter' },
    { nyckel: 'åtgärd', etikett: 'Åtgärder' },
    { nyckel: 'kalender', etikett: 'Kalender' },
    { nyckel: 'grupprum', etikett: 'Grupprum' },
    { nyckel: 'material', etikett: 'Material' },
  ];

  const t = $derived(insp.trender);
  const klass = $derived(t?.group || '');
  const lektioner = $derived(t?.lessons ?? 0);
  const analyserade = $derived(t?.analysed ?? 0);
  const counts = $derived(t?.counts || {});
  const oppna = $derived(t?.actions?.open ?? 0);
  const klara = $derived(t?.actions?.done ?? 0);
  const summa = $derived(oppna + klara);
  const procent = $derived(summa ? Math.round((klara / summa) * 100) : 0);
  const svarigheter = $derived(t?.top_difficulties || []);
</script>

<!-- null = ingen klass vald, eller hämtningen föll → ingen panel. -->
{#if t}
  <section class="panel">
    <div class="huvud">
      <h2 class="rubrik">
        Terminstrender{#if klass}<span class="klass">{" · " + klass}</span>{/if}
      </h2>
      {#if lektioner}
        <span class="andel">{analyserade} av {lektioner} lektioner analyserade</span>
      {/if}
    </div>

    {#if !lektioner}
      <!--
        KLASS VALD MEN INGA LEKTIONER är ett tomtillstånd, till skillnad från
        "klass vald, lektioner finns, inget analyserat" — då står räknarna på
        noll, och nollor är ett svar. Specens avsnitt 4.
      -->
      <p class="tomt">
        Inga lektioner för den här klassen ännu — terminens mönster växer fram
        när du transkriberat och analyserat några.
      </p>
    {:else}
      <div class="raknare">
        {#each RAKNARE as r (r.nyckel)}
          <div class="post">
            <span class="etikett">{r.etikett}</span>
            <span class="tal" class:noll={!counts[r.nyckel]}>{counts[r.nyckel] || 0}</span>
          </div>
        {/each}
      </div>

      <!-- Balken döljs helt när det inte finns några åtgärder, som i gamla
           appen. Ett tomt spår med "0 %" påstår mer än det vet. -->
      {#if summa}
        <div class="balk">
          <div class="balkrad">
            <span class="balketikett">Avklarade åtgärder</span>
            <span class="balktal">{klara}/{summa} · {procent} %</span>
          </div>
          <!-- Samma form som progressbaren i Korning.svelte:232-239: 3px spår,
               2px radie. Gamla appens pillerformade 99px-balk följer inte med. -->
          <div class="spar">
            <div class="fyllnad" style="width: {procent}%"></div>
          </div>
        </div>
      {/if}

      <p class="etikett rubriketikett">Återkommande svårigheter</p>
      {#if svarigheter.length}
        <ul class="lista">
          {#each svarigheter as d (d.text)}
            <li>
              <span class="bricka" class:ater={d.count > 1}>{d.count}×</span>
              <span class="svarighet">
                {d.text}{#if d.refs?.length}<span class="ref">{" (" + d.refs.join(', ') + ")"}</span>{/if}
              </span>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="tomt">
          Inga svårigheter registrerade än — analysera lektioner för att se
          mönster över terminen.
        </p>
      {/if}
    {/if}
  </section>
{/if}

<style>
  /* Identisk panelform som Agenda.svelte och NastaLektion.svelte. */
  .panel {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 16px 18px;
    margin-bottom: 14px;
  }

  .huvud {
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
  }
  .rubrik {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--ink);
    margin: 0;
  }
  .klass { font-weight: 400; color: var(--ink-3); }
  .andel {
    margin-left: auto;
    font-size: 0.72rem;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }

  .tomt {
    font-size: 1.03rem;
    color: var(--ink-2);
    max-width: 52ch;
    margin: 10px 0 0;
  }

  /* Räknarna: en wrappande rad, avgränsad med hårlinjer i stället för fem
     rutor. Ingen ram, ingen fyllning, inga 22px-siffror. */
  .raknare {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 22px;
    margin: 14px 0 0;
    padding: 12px 0;
    border-top: 1px solid var(--line);
    border-bottom: 1px solid var(--line);
  }
  .post { display: flex; align-items: baseline; gap: 7px; }
  .etikett {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .tal {
    font-size: 1.03rem;
    font-weight: 600;
    color: var(--ink);
    font-variant-numeric: tabular-nums;
  }
  /* En nolla är ett svar, men inte ett som ska dra blicken. */
  .tal.noll { color: var(--ink-3); font-weight: 400; }

  .balk { margin-top: 16px; }
  .balkrad {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 6px;
  }
  .balketikett { font-size: 1.03rem; color: var(--ink-2); }
  .balktal {
    font-size: 0.72rem;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }
  .spar {
    height: 3px;
    background: var(--track);
    border-radius: 2px;
    overflow: hidden;
  }
  .fyllnad { height: 100%; background: var(--accent); border-radius: 2px; }

  .rubriketikett { margin: 20px 0 8px; }

  .lista {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .lista li {
    display: flex;
    align-items: baseline;
    gap: 10px;
    font-size: 1.03rem;
    color: var(--ink);
  }
  .bricka {
    flex: none;
    min-width: 28px;
    text-align: center;
    border-radius: 3px;
    padding: 1px 5px;
    font-size: 0.72rem;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
    background: var(--sunken);
    color: var(--ink-3);
  }
  /* Accenten markerar att svårigheten ÅTERKOM — ett live-tillstånd i datan, som
     är vad One Voice reserverar den för. */
  .bricka.ater { background: var(--accent-weak); color: var(--accent); }
  .svarighet { min-width: 0; overflow-wrap: anywhere; }
  .ref { color: var(--ink-3); font-size: 0.72rem; }
</style>
