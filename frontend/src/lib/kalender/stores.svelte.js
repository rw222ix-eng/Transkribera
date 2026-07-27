// Kalenderförslaget som kan uppstå ur lektionschatten. Ett enda förslag åt
// gången, precis som chattens tråd hör till EN lektion åt gången — hör
// alltså ihop med `chatt` (lektionschatt/stores.svelte.js) och nollställs av
// samma nollstall()-anrop, via kalender/actions.js:nollstallForslag().
//
// Ingen `calQ` här: frågekortet är nästa omgångs modal (se kalender/tagg.js:
// tolkaFragor, som redan finns men bara används för ett textbesked i den
// här omgången).
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
  // aldrig — den visas nu i Forslagsbox.
  hint: '',
});
