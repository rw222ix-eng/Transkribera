# Koppla Google Kalender

Kalendersynken läser lektionerna ur Google Kalender och skriver tillbaka
godkända tavlor och prov som poster (app/calendar_google.py). Vad som får läsas
ur en händelses beskrivning står vid `_AVDELARE` i samma fil.

## Engångsuppsättningen

1. I Google Cloud Console: slå på **Google Calendar API**, sätt upp *OAuth
   consent screen* och skapa en **OAuth client ID** av typen **Desktop app**.
   Ladda ner klient-JSON:en.
2. Lägg filen som **`google_client_secret.json`** i appens basmapp
   (repo-roten i utvecklingsläge, bredvid exe:n i den paketerade appen), eller
   skicka den till `POST /api/calendar/client-secret`. Filen är gitignorerad.
3. Anslut med `POST /api/calendar/connect`. Webbläsaren öppnar Googles
   inloggning. Token sparas lokalt i `google_token.json` (också gitignorerad).
   `POST /api/calendar/disconnect` kopplar bort kontot så ett annat kan
   anslutas.

Klienten kan också ges som miljövariabeln `TRANSKRIBERA_GOOGLE_CLIENT` (rå
JSON) eller som `google_client_secret.json` inbyggd i PyInstaller-bunten
(`sys._MEIPASS`). Ett client secret av typen Desktop app räknar Google inte som
hemligt, men det checkas ändå aldrig in.

## Felsökning

- **"Google-biblioteken saknas …"**: `pip install -r requirements.txt`
  (`google-api-python-client` och `google-auth-oauthlib`).
- **"Ingen OAuth-klientfil hittades …"**: filen ligger inte i basmappen.
  Meddelandet visar sökvägen appen letar i.
- **"Anslutningen misslyckades …"**: samtycket avbröts eller klienten är fel
  konfigurerad. Kontrollera att Calendar API är påslaget.
