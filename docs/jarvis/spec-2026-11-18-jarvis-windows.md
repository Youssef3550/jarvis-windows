# Taak: Coqui TTS integreren als stemuitvoer voor Hasan

## Doel
Vervang de huidige tekst-naar-spraak engine (waarschijnlijk browser SpeechSynthesis) door Coqui TTS, zodat Hasan een mooie, constante Engelse stem heeft. Gebruik een ingebouwde Engelse stem van Coqui (bij voorkeur Brits of neutraal Engels, mannelijk).

## Stappen
1. Lees de projectstructuur en zoek waar de TTS momenteel geïmplementeerd is (frontend of server).
2. Installeer Coqui TTS via pip als het nog niet geïnstalleerd is (`pip install TTS`).
3. Voeg een `/tts` endpoint toe aan de Python server dat tekst ontvangt en audio teruggeeft (WAV of MP3).
4. Gebruik een goede ingebouwde Coqui stem, bij voorkeur `tts_models/en/vctk/vits` (speaker p273 of p330 voor een Brits mannelijk geluid) of een vergelijkbaar model.
5. Pas de frontend aan zodat die het `/tts` endpoint gebruikt in plaats van de browser SpeechSynthesis.
6. Zorg dat de audio vloeiend afspeelt in de browser.
7. Houd de optie voor stemklonen open (voeg commentaar toe in de code waar dat later toegevoegd kan worden).

## Voorkeur
- Volledig gratis, lokaal, geen API-sleutels nodig
- Zo min mogelijk wijzigingen aan de bestaande structuur
- Hasan moet na de wijziging nog steeds werken zoals voorheen

## Acceptatiecriteria
- Hasan spreekt met een Coqui stem in plaats van de browser stem
- De stem klinkt natuurlijk en verstaanbaar
- Stemklonen is voorbereid in de code voor later