# FunkGateway TeamSpeak 3 Audio Bridge

Dieses Plugin nimmt 48-kHz/16-Bit/Mono-PCM ausschließlich über
`127.0.0.1:39582/UDP` von FunkGateway entgegen und mischt es direkt in den
TeamSpeak-3-Capture-Pfad.

Während FunkGateway Audio einspeist, schaltet das Plugin TeamSpeak kurz auf
Continuous Transmission. Danach wird der vorherige PTT/VAD-Zustand
wiederhergestellt.

## Installation

Die Release-Datei `FunkGateway-Audio-Bridge.ts3_plugin` doppelklicken und
TeamSpeak 3 danach neu starten. Alternativ liegt die DLL im Release-ZIP unter
`teamspeak-plugin\plugins\FunkGatewayAudioBridge_win64.dll`.

Das Plugin lauscht ausschließlich auf localhost. Es öffnet keinen Port nach
außen.
