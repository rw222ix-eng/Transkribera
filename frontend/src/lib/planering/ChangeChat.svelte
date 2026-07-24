<script>
  import { plan } from './stores.svelte.js';
  import { refineBoard } from './actions.js';

  const canSend = $derived(
    plan.chatInput.trim().length > 0 && !!plan.id && plan.phase !== 'running',
  );
</script>

{#if plan.id}
  <div class="chat">
    <span class="label">Ändra</span>
    <input
      class="field"
      aria-label="Ändra tavlan"
      placeholder="Be om en ändring — t.ex. lägg till ett exempel med bråk"
      bind:value={plan.chatInput}
      onkeydown={(e) => { if (e.key === 'Enter' && canSend) refineBoard(); }}
    />
    <button class="send" disabled={!canSend} onclick={() => refineBoard()}>Skicka</button>
  </div>
{/if}

<style>
  .chat {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    margin-top: 24px;
  }
  .label {
    flex: 0 0 74px;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .field {
    flex: 1;
    min-width: 240px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 12px 14px;
    font-family: inherit;
    font-size: inherit;
    color: var(--ink);
  }
  .send {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 11px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .send:disabled { opacity: 0.55; cursor: default; }
</style>
