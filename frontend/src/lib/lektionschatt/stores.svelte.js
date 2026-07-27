// Lektionschatten (plan B4). Modalen öppnas i dag från lektionskortet och
// senare även från arkivsvarets källor (plan B3), så tillståndet bor här och
// inte i någon av vyerna.
export const chatt = $state({
  open: false,
  lektionId: null,      // history_id — nyckel både för API:t och för samtalskartan
  namn: '',             // rubriken

  segment: [],          // [{start, end, text}] — SERVERNS form, som i transkript/
  laddar: false,        // segmenthämtningen är i luften

  // Statusraden är SYNLIG och bär fel. Live-regionen bär `annons`, som är en
  // annan text: ett växande svar får aldrig annonseras token för token, men
  // det FÄRDIGA svaret ska läsas upp — och det ska inte samtidigt dubbleras
  // på skärmen under tråden.
  besked: '',
  beskedArt: 'fel',     // 'fel' | 'info'
  annons: '',           // bara live-regionen

  trad: [],             // [{roll: 'anvandare'|'modell', text, resonemang}]
  utkast: '',           // skrivradens råtext
  skickar: false,       // sant till done ELLER error — aldrig släckt vid första token
  tank: false,          // "Tänk djupare"

  resonemangOppet: {},  // {meddelandeindex: bool}
  valtCitat: null,      // {mi, segIndex} eller null
});
