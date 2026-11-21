Forwarder vocabulary for reading customer and carrier mail (DE, IT, ES, FR, EN). Map every term to the field.

Weight and volume
- gross weight, Bruttogewicht, brutto, peso lordo, peso bruto, poids brut -> actual_kg (total, not per piece)
- "je/each/ciascuno/cada una/à 38 kg" -> per piece: multiply by pieces
- t, to, Tonne, tonnellata -> x 1000 kg. lbs, lb -> x 0.45359237 kg
- German and Italian numbers: "1.450 kg" = 1450 kg, "0,9 cbm" = 0.9 cbm
- cbm, m3, m³, CBM, Kubikmeter, metri cubi -> volume_cbm
- dimensions L x B x H / L x W x H in cm -> cbm = pieces x L x W x H / 1,000,000
- chargeable weight, frachtpflichtiges Gewicht, peso tassabile -> code computes it, never the model

Pieces
- Kolli, Colli, colli, Packstücke, Kartons, cartons, boxes, cajas, colis, crates, skids, pallets, Paletten -> pieces

Places
- Abholung, Abholadresse, ritiro, pickup, door-to-airport -> pickup address. Take the 5-digit postcode
- Anlieferung durch uns, we deliver to the airport -> no pickup
- city or country instead of an airport code: map a city to its IATA code. A country alone is missing information

Preference
- cheapest, günstigste, più economica, más económica, moins chère -> cheapest
- fastest, schnellste, eilig, dringend, urgente, so schnell wie möglich, ASAP -> fastest
- a deadline ("must arrive by Wednesday") -> fastest
- "cheapest and fastest" -> quote one option only. Take cheapest and say why

Special cargo, flag it, do not price it blind
- DG, Gefahrgut, merci pericolose, UN numbers (UN3480 lithium), class 1 to 9 -> dangerous_goods
- live animals, lebende Tiere, animali vivi -> live_animal
- oversize, sperrig, over 3 m high -> oversize

Mail kinds
- Angebot, Anfrage, richiesta quotazione, cotización, demande de cotation, RFQ, quote -> rfq
- we accept, book it, buchen, confermiamo -> accept
- too expensive, zu teuer, troppo caro, competitor offered -> negotiation (carriers do not negotiate)
- where is, Status, dov'è -> tracking
- Abwesenheitsnotiz, out of office -> noise
- Fwd/WG chains: the newest text on top wins over quoted older values

Carrier terms
- fuel surcharge, FSC, Treibstoffzuschlag, and security surcharge, SSC -> per kg of billed weight
- minimum, Mindestfracht, M -> applies to freight before surcharges
- rate ID -> book with it within 15 min
- AWB, Luftfrachtbrief -> air waybill number (tracking)
