# Aktivera Google Kalender-integrationen

Transkribera kan skapa kalenderhändelser i din egen Google Kalender från
kalenderförslagen i lektionsvyn. Integrationen är **inbyggd och färdigkopplad**
— men den är avstängd tills du lägger in din egen OAuth-klientfil. Det här är
ett medvetet undantag från appens offline-princip: **bara** den titel och
anteckning du själv godkänner med **"Lägg till"** skickas till Google, aldrig
transkript, elevdata eller annat lektionsinnehåll.

## Engångsuppsättning

1. Öppna [Google Cloud Console](https://console.cloud.google.com/) och skapa
   (eller välj) ett projekt.
2. Aktivera **Google Calendar API** för projektet
   (*APIs & Services → Enable APIs and Services → Google Calendar API*).
3. Under *APIs & Services → OAuth consent screen*: välj **External**, fyll i det
   som krävs och lägg till din egen Google-adress som **testanvändare**.
4. Under *APIs & Services → Credentials → Create credentials → OAuth client ID*:
   välj apptyp **Desktop app**. Ladda ner klient-JSON:en.
5. Spara filen som **`google_client_secret.json`** i appens basmapp
   (repo-roten när du kör i utvecklingsläge; bredvid exe:n i den paketerade
   appen). Filen är gitignorerad och ska aldrig checkas in.

## Använda den

1. Öppna en inspelning → ställ en fråga som rör tid/prov/läxa/påminnelse, så
   dyker kalenderförslaget upp (eller det visas automatiskt när det är relevant).
2. Klicka **"Anslut Google-konto"**. Din webbläsare öppnar Googles
   samtyckesflöde — godkänn. Åtkomsttoken sparas lokalt i `google_token.json`
   (också gitignorerad).
3. Justera titel, datum/tid och anteckning vid behov och klicka **"Lägg till"**.
   Händelsen skapas i din primära kalender.

## Felsökning

Om något saknas visar appen ett felmeddelande (en fel-toast nere på skärmen)
som talar om exakt vad som fattas:

- **"Google-biblioteken saknas …"** — kör `pip install -r requirements.txt`
  (paketen `google-api-python-client` och `google-auth-oauthlib`).
- **"Ingen OAuth-klientfil hittades …"** — du har inte lagt
  `google_client_secret.json` i basmappen (steg 5 ovan). Meddelandet visar
  den exakta sökväg appen letar i.
- **"Anslutningen misslyckades …"** — samtycket avbröts eller klienten är fel
  konfigurerad; kontrollera att Calendar API är aktiverat och att du är
  tillagd som testanvändare.

Ta bort `google_token.json` för att koppla från kontot.
