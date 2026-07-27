// Kalenderförslaget som kan uppstå ur lektionschatten, plus de tre modalerna
// som hör till kalenderflödet: frågekortet (STEG 1), anteckningsmodalen och
// Google-kopplingsguiden. Ett enda förslag åt gången, precis som chattens
// tråd hör till EN lektion åt gången — hör alltså ihop med `chatt`
// (lektionschatt/stores.svelte.js) och nollställs av samma nollstall()-anrop,
// via kalender/actions.js:nollstallForslag().
export const kal = $state({
  // {titel, nar, startIso, slutIso, slutDag, anteckning, tillagd, upptagen,
  // lank} eller null. `nar` är etikettformen "fre 17 jul · 14:30" —
  // `startIso` vinner vid Lägg till (se tid.js:starttidFor). Svenska
  // motsvarigheter till gamla appens lessonChatEvent (app.js:57).
  forslag: null,

  // Google-anslutningen. null = ännu inte kontrollerad.
  ansluten: null,
  klientKlar: null,
  // Serverns förklaring när något saknas (t.ex. "Ingen OAuth-klientfil
  // hittades"). D6 (rekon §11): gamla appen sparade denna men läste den
  // aldrig — visas nu både i Forslagsboxens statusrad och i
  // GoogleAnslutModal, i just den guide där hjälptexten faktiskt behövs.
  hint: '',

  // Kalendermodalens klargörande frågor (calQ i gamla appen, STEG 1 i
  // llm_client._cal_instr). null = inget frågekort öppet. Gamla appens
  // `calQ.which` ('lesson'|'ask') behövs inte — arkivsvarets kalenderväg
  // portas inte (bindande beslut #1), så det finns bara EN väg hit.
  fragor: null, // {fragor: [{fraga, alternativ, val}], fritext: string} | null

  // Anteckningsmodalen — läser OCH redigerar forslag.anteckning i ett större
  // fält än Forslagsboxens klippta förhandsvisning.
  anteckningOppen: false,

  // Google-kopplingsguiden (calSetupOpen i gamla appen).
  guideOppen: false,
  guideBusy: false, // installation/inloggning pågår
});
