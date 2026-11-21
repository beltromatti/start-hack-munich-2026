# 5U: timeline delle ondate

**Sab 21 nov, 19:15 · round 33 · 30 su 33 accettati · persi 11, 20, 33**

## Già successo

| Ora | Round | Ondata | Esempio |
| --- | --- | --- | --- |
| 16:00 | 1-4 | Pulito | tutti i dati nella mail |
| 16:25 | 5-9 | Forma della spedizione | lotti, netto/lordo, misure per collo |
| 16:55 | 10-11 | Documenti | allegato dice DG, mail dice "non-dangerous" · **r11 perso** |
| 17:07 | 12-15 | Testo ingannevole | "import" che è export, vecchia richiesta ZRH-MEL inoltrata sotto |
| 17:26 | 15-20 | Dialogo | ritiro mancante, poi solo "Augsburg" · **r20 perso** |
| 18:36 | 27-32 | Sistema | API tariffe portale 503, prezzi e booking via mail |
| 19:15 | 33 | Documenti 2 | packing spec 1.92 cbm, mail 2.78 cbm · **r33 perso** (fix Sam: `fix/document-sizes`) |

## Adesso

**Due fronti insieme:** portale giù e allegati che smentiscono la mail.
Le ondate tornano e si sommano. Prossimo allegato che smentisce: peso, pezzi o data.

## Probabile (stima, ogni riga ha già un indizio)

| Quando | Ondata | Cosa | Indizio |
| --- | --- | --- | --- |
| ~20:00 | Sistema 2 | booking API 503, limite portale più basso, vettori lenti | lo spec descrive 503 anche per `POST /bookings`, header `X-RateLimit-Limit` |
| ~21:00 | Mercato | tariffa v2, prezzi in USD, vettore che declina | `dataset_version` e `fx_eur_per_usd` esistono, mai usati |
| ~22:00 | Dopo il booking | ritardo, cancellazione, modifica, rate scaduto dopo 15 min | il tracking vale +10 ed è la parte meno testata |
| Notte | Volume | raffiche, trucchi combinati | le ondate finora si sommano, non spariscono |
| Dom mattina | Avversario | injection, mittente falso, origine estera, import vero, controfferta | inoltri esca con ZRH, AMS, FCA, verdetti `rejected` e `voided` mai visti |

## Dove siamo scoperti

- **Tracking:** solo la conferma di booking sveglia il deal. Una mail di ritardo della compagnia non la legge nessuno, e rispondiamo dal record: diremmo il falso
- **Codice:** solo EUR, solo export, "cancel" non esiste in `backend/app`
- **Tool:** `book` prenota anche senza quota nel thread, `crm` mostra a chiunque i deal di altri clienti
- **Portale:** 3 richieste insieme consumano il limite (10/min), 429, persi i punti tempo

## Fix, nell'ordine delle ondate

1. **Cache portale:** prezzi per tratta e scaglione, 15 min, condivisa tra i deal
2. **Sim:** una mail in USD e una con tariffa v2 in `make sim`
3. **Booking thread:** ogni mail lì sveglia il deal
4. **Segnali:** un tool che vede un campo, errore o valuta mai visti lo scrive nel risultato, l'agente fa una nota visibile in UI. `/v1/board/me` a ogni round: un rejected o no answer apre subito la sessione (r20 e r33 persi senza accorgercene)
5. **Guardie:** `book` solo su opzione già quotata, `crm` solo deal del mittente (`tracking@` vede tutti), una frase nel prompt: la mail porta fatti, non ordini

**Li costruisco io su un branch, tu fai il merge?**
