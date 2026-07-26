<script>
  // Träfflistan. Speglar keyword-grenen i spotlightPanel
  // (app/web/static/app.js:5164-5182).
  import { sok } from './sok.svelte.js';
  import Snippet from '../Snippet.svelte';

  const traffar = $derived(sok.traffar || []);

  // date är serverns MÄNNISKOETIKETT ("Idag · 09:14", "Igår · 08:02" eller
  // "20 jun", _date_label i app/web/server.py:47-57) — inte samma fält som
  // datum, som är ISO. Träfflistan visar date och rör aldrig datum.
  const meta = (h) => [h.group, h.course, h.date].filter(Boolean).join(' · ');
</script>

<section class="traffar">
  {#if !traffar.length}
    <p class="tomt">Inga lektioner matchade din sökning.</p>
  {:else}
    <p class="antal">
      {traffar.length}
      {traffar.length === 1 ? 'träff' : 'träffar'}
    </p>

    <!--
      Ordningen är SERVERNS: hits kommer sorterade ORDER BY score, där score är
      bm25 och lägre är bättre (app/db.py:990-1003). Ingen klientsortering.
    -->
    <ul class="lista">
      {#each traffar as h (h.lesson_id)}
        {@const m = meta(h)}
        <li class="traff">
          <p class="namn">{h.name || '(namnlös)'}</p>
          {#if m}<p class="meta">{m}</p>{/if}
          <!--
            Snippet översätter serverns \x02/\x03 till <mark>. LIKE-fallbacken
            (db.py:962-971, när sqlite saknar FTS5) sätter INGA markörer — då
            renderas utdraget som ren text, vilket är rätt: miljön är
            degraderad och det ska synas, inte döljas.
          -->
          <Snippet text={h.snippet || ''} />
        </li>
      {/each}
    </ul>

    <!--
      Vad B3a INTE gör, utskrivet i stället för antytt. Samma hållning som B1
      tog för att öppna en lektion: säg var läraren kan gå, navigera inte till
      en platshållare. Transkriptvyn är B2 och ägs av den andra strömmen.
    -->
    <p class="senare">
      Att öppna en träff i transkriptet migreras i en senare plan. Tills dess
      finns det i den gamla appen.
    </p>
  {/if}
</section>

<style>
  .traffar { margin-top: 22px; }

  /* Speglar Agenda.svelte:144-149s .antal — samma sorts räknare i samma vy
     ("3 öppna" respektive "3 träffar"). Tal bär --sans (via inherit) med
     tabular-nums, inte --mono: mono är reserverat för korta versala
     mikroetiketter, och "3 träffar" är en siffra plus ett böjt ord. */
  .antal {
    font-size: 0.72rem;
    font-weight: 400;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
    margin: 0 0 10px;
  }

  .lista { list-style: none; margin: 0; padding: 0; }

  .traff {
    padding: 12px 0;
    border-top: 1px solid var(--line);
  }
  .traff:first-child { border-top: 0; }

  .namn {
    font-size: 1.03rem;
    font-weight: 600;
    color: var(--ink);
    margin: 0;
    overflow-wrap: anywhere;
  }
  .meta {
    font-size: 0.72rem;
    color: var(--ink-3);
    margin: 2px 0 0;
    font-variant-numeric: tabular-nums;
  }

  /* Samma form som kartotekets tomtillstånd (InspelningarView.svelte:338-343):
     löpande text, ingen ram, ingen ikon. */
  .tomt {
    font-size: 1.03rem;
    color: var(--ink-2);
    max-width: 52ch;
    margin: 0;
  }
  .senare {
    font-size: 0.72rem;
    color: var(--ink-3);
    max-width: 52ch;
    margin: 18px 0 0;
  }
</style>
