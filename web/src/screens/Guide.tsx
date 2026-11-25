import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { api } from "../api";
import { currentMonth, formatAmount, formatMonths, monthBounds } from "../format";
import type { Metrics } from "../types";

export type GuideTopic =
  | "month"
  | "statistics"
  | "budget"
  | "liquidity"
  | "typical"
  | "rare"
  | "refund"
  | "contribution"
  | "reserve"
  | "expected"
  | "runway"
  | "essential"
  | "transfer"
  | "virtual"
  | "rule"
  | "tag"
  | "anomaly"
  | "check"
  | "sync-limit"
  | "goal"
  | "contribution-base"
  | "deduction-cap"
  | "scenario"
  | "coast-fi"
  | "withheld"
  | "opening"
  | "twr"
  | "mwr"
  | "accrual"
  | "service"
  | "coverage";

interface Card {
  id: GuideTopic;
  title: string;
  /** What it means. */
  means: ReactNode;
  /** How it is computed, where something is. */
  computed?: ReactNode;
  /** What changing it does. */
  changes?: ReactNode;
  /** The figure on this ledger today, when the concept has one. */
  now?: (metrics: Metrics) => string | null;
}

function amount(value: string | null): string | null {
  return value === null ? null : formatAmount(value);
}

const CARDS: Card[] = [
  {
    id: "month",
    title: "Questo mese e il solito",
    means:
      "In cima: quanto è a tuo carico finora in questo mese, cioè quanto è uscito tolti i rimborsi e la parte pagata dai contributi. Sotto, la spesa lorda, i contributi, le entrate e la differenza fra entrate e spesa a tuo carico, ognuna accanto al mese prima.",
    computed:
      "Il mese prima si legge due volte: fino allo stesso giorno, per confrontare gli stessi giorni, e intero. Le spese rare ci sono. I contributi contati sono quelli che hanno coperto qualcosa: su ogni conto al massimo quanto quel conto ha speso, così spesa lorda meno contributi fa la cifra a tuo carico. Le entrate sono quelle del grafico Entrate e uscite, senza giroconti, rimborsi e contributi. Il netto dipende dal giorno in cui arriva un contributo: per questo la spesa lorda resta accanto.",
    changes:
      "Dove sono finiti elenca le categorie con una spesa in questo mese, dalla più alta, ognuna con la distanza dal suo solito: la mediana dei 6 mesi completi precedenti tagliati allo stesso giorno, senza spese rare e senza contributi. Un tocco apre i suoi movimenti.",
  },
  {
    id: "statistics",
    title: "Mediana e media",
    means:
      "La mediana è il mese normale: metà dei mesi sta sotto e metà sopra, e una spesa eccezionale non la sposta. La media dice quanto costa una categoria nel lungo periodo: è la cifra da mettere da parte se spende solo ogni tanto.",
    computed:
      "Sui mesi completi scelti, 6, 12 o 24, senza quello in corso. Un mese senza spese vale zero. Le spese sono al netto dei rimborsi e non dei contributi, e le spese rare ci sono: è lo stesso conto del Budget, così le cifre si confrontano con un tetto. Il Di solito del Budget è la mediana o la media dei 3, 6 o 12 mesi completi prima del mese che guardi. Le mediane delle categorie non sommano a quella del totale.",
    changes:
      "Se mediana e media sono lontane la categoria va a strappi: un tetto sulla mediana salta nei mesi forti, e per quelli serve un tetto del solo mese.",
  },
  {
    id: "budget",
    title: "Budget e voci",
    means:
      "Il budget di una categoria è quanto vuoi spendere lì in un mese. Una voce è una spesa che sai già di dover fare: si scrive con descrizione e importo, e la categoria può aspettare.",
    computed:
      "Il tetto del mese è quello solo di quel mese, se c'è, altrimenti il default scritto da un mese in poi; se non hai scritto nessun tetto ma la categoria ha delle voci, il budget è la loro somma. Una voce senza categoria prende quella di una regola di categoria che riconosce la sua descrizione, e altrimenti resta Da assegnare e non conta finché non ne ha una. Il confronto è con la mediana o la media dei mesi completi prima, 3, 6 o 12: per ogni categoria, e per il totale contro le stesse categorie lette come un'unica spesa, accanto a tutta la spesa del mese.",
    changes:
      "Un tetto scritto a mano resta tuo: le voci che lo superano si segnalano, e non lo alzano. Per categoria mostra i tetti, Per voce tutte le spese del mese con le Da assegnare in cima; le categorie senza budget si nascondono finché non chiedi di vederle.",
  },
  {
    id: "liquidity",
    title: "Liquidità",
    means: "Quanto c'è adesso, spendibile: la somma dei saldi dei conti reali.",
    computed:
      "Per un conto collegato è il saldo che risulta dai movimenti; per il broker è la liquidità che dichiari tu con Aggiorna la liquidità. I titoli non ci sono: il portafoglio non è seguito.",
    changes: "Cambia con ogni movimento e ogni dichiarazione del broker.",
    now: (metrics) => amount(metrics.liquidity),
  },
  {
    id: "typical",
    title: "Spesa mensile tipica",
    means: "Quanto resta a tuo carico in un mese normale, senza le spese rare e tolti i contributi.",
    computed:
      "Il valore centrale (la mediana) degli ultimi 6 mesi completi. Un mese strano non la sposta: sposta la riga solo se si ripete.",
    changes: "Segnare una spesa come rara la toglie da qui e la porta nella riserva.",
    now: (metrics) => amount(metrics.recurring_burn),
  },
  {
    id: "rare",
    title: "Spesa rara",
    means:
      "Una spesa che capita poco: un viaggio, un elettrodomestico, una riparazione. Non dice niente su come va un mese normale.",
    computed:
      "Si dice in due modi, che contano allo stesso modo: un'intera categoria (Viaggi) o un tag su singoli movimenti (il frigorifero in Casa). Vale per tutto il movimento.",
    changes:
      "Esce dalla spesa tipica, da Questo mese e dalle anomalie, ed entra nella riserva. Se un movimento è sia raro sia irrinunciabile, vince raro.",
  },
  {
    id: "refund",
    title: "Rimborso",
    means:
      "Soldi che tornano per una spesa: un amico che ti ridà la sua parte, un negozio, un'assicurazione, la valuta avanzata da un viaggio.",
    computed:
      "Un accredito messo in una categoria abbassa quella categoria nel mese in cui arriva, con i tag del movimento. Non serve abbinarlo alla spesa: basta la stessa categoria. Può rendere negativo un mese.",
    changes:
      "Stipendio ed Entrate portano il segno Entrata: lì un accredito è un'entrata, non un rimborso. Un accredito senza categoria non conta come rimborso: da agosto 2026 lo trovi in Da confermare, in Accrediti da chiarire, dove scegli se è entrata, rimborso o contributo. Quando ha una categoria esce da lì, e si ritrova in Movimenti filtrando per categoria. Chi ti deve ancora dei soldi non si segue: finché non paga, la spesa resta alta.",
  },
  {
    id: "contribution",
    title: "Contributo alle spese",
    means:
      "Soldi che arrivano per coprire le spese in generale e non una spesa precisa: per esempio i versamenti di chi condivide con te un conto comune.",
    computed:
      "Un accredito in una categoria col segno Contributo alle spese abbassa il totale e nessuna categoria. Copre tutte le spese del conto su cui arriva, rare comprese: in ogni mese tutto ciò che quel conto ha pagato scende della stessa percentuale, e gli altri conti restano interi. Riduce spesa tipica, riserva per spese rare e spesa attesa, quindi allunga i mesi di autonomia, e in cima al cruscotto dà la cifra a tuo carico. Dove sono finiti resta lordo.",
    changes:
      "Non è un'entrata né un rimborso. Il segno sta da solo: accenderlo spegne Spesa rara, Irrinunciabile ed Entrata. I mesi di autonomia contano che i contributi continuino anche se le tue entrate si fermano.",
    now: (metrics) => amount(metrics.contributions_monthly),
  },
  {
    id: "reserve",
    title: "Riserva per spese rare",
    means: "Quanto mettere da parte ogni mese per quando le spese rare tornano.",
    computed:
      "Le spese rare degli ultimi 24 mesi completi, tolti i loro rimborsi e la parte coperta dai contributi, divise sempre per 24. Con meno di 24 mesi di storia è sottostimata: le spese ci sono, i mesi no.",
    changes: "Cresce quando segni qualcosa come raro.",
    now: (metrics) => amount(metrics.episodic_accrual),
  },
  {
    id: "expected",
    title: "Spesa mensile attesa",
    means: "Quanto costa davvero un mese, contando anche quello che capita di rado.",
    computed: "Spesa mensile tipica più riserva per spese rare.",
    now: (metrics) => amount(metrics.expected_burn),
  },
  {
    id: "runway",
    title: "Mesi di autonomia",
    means: "Per quanti mesi ce la fai se le tue entrate si fermano.",
    computed: "Liquidità divisa per la spesa mensile attesa, che è già al netto dei contributi alle spese.",
    now: (metrics) => (metrics.runway_months === null ? null : formatMonths(metrics.runway_months)),
  },
  {
    id: "essential",
    title: "Irrinunciabile e tagliabile",
    means:
      "Irrinunciabile è la spesa che non taglieresti; tagliabile è tutto il resto. Entrambe dicono quanto resta a tuo carico: i contributi alle spese le riducono in proporzione, sul conto su cui arrivano.",
    computed:
      "La mediana degli ultimi 6 mesi di ciò che porta il segno Irrinunciabile, su una categoria o su un tag.",
    changes: "Accendere il segno sposta la spesa da una all'altra; il totale resta lo stesso.",
    now: (metrics) =>
      metrics.essential_monthly === null || metrics.discretionary_monthly === null
        ? null
        : `${formatAmount(metrics.essential_monthly)} e ${formatAmount(metrics.discretionary_monthly)}`,
  },
  {
    id: "transfer",
    title: "Giroconto",
    means:
      "Soldi che passano da un tuo conto a un altro: non sono né spesa né entrata, e Movimenti li nasconde di base.",
    computed:
      "Due movimenti di pari importo e segno opposto su conti diversi, a non più di due giorni, vengono proposti in Da confermare. Il nome del conto stampato dalla banca conferma la coppia. A mano si possono abbinare anche due movimenti fino a sette giorni di distanza.",
    changes:
      "Rifiutare un giroconto riporta i due movimenti fra le spese da categorizzare. Una regola può registrarne uno anche quando l'altra metà non è qui.",
  },
  {
    id: "virtual",
    title: "Conto virtuale",
    means:
      "Il posto dove va a finire un giroconto la cui altra metà non è su un conto reale: Investimenti, per esempio. Non conta nella liquidità.",
    computed:
      "Un conto creato a mano invece è reale: la regola ci scrive il movimento opposto, e con Saldo dai movimenti il suo saldo segue i giroconti. Gli interessi si correggono con un movimento.",
    changes:
      "Un conto collegato che riporta l'acquisto ma non la ricarica che lo paga, come PayPal con la carta, segna Non riporta le ricariche in Conti: una regola di giroconto sulla banca, verso quel conto, ci scrive la ricarica, e l'acquisto resta contato una volta sola.",
  },
  {
    id: "rule",
    title: "Regola",
    means:
      "Vale per ogni movimento la cui descrizione contiene il suo testo, senza badare alle maiuscole: «addebito sdd» li prende tutti, «amazon prime» solo quelli. Fra barre è un'espressione regolare: /amazon (eu|payments)/ prende una famiglia che la banca scrive in troppi modi.",
    computed:
      "Se due testi combaciano vince il più lungo, e a parità quello più ristretto: una regola si può limitare a un conto e a un intervallo di importi. Oltre ad assegnare una categoria può cancellare, registrare un giroconto o mettere un tag. Cancellare vince su giroconto, giroconto su categoria; il tag si somma sempre.",
    changes:
      "Si applica subito. Rinominare una categoria non le toglie niente: le sue regole la seguono. Correggerla sposta i movimenti che teneva; rimuoverla li lascia alla regola più ampia che combacia ancora, o a Da confermare. Una categoria decisa a mano non si tocca.",
  },
  {
    id: "tag",
    title: "Tag",
    means:
      "Un'etichetta libera su un movimento, che sta insieme alla categoria: un viaggio che attraversa più categorie, per esempio.",
    computed:
      "Si mette a mano, su uno o più movimenti, o con una regola. Può portare gli stessi segni di una categoria, Spesa rara e Irrinunciabile.",
    changes:
      "Si filtra in Movimenti e nella Dashboard. Un tag messo a mano sopravvive a cancellazione e ripristino, come la nota; togliere una regola toglie solo i tag messi da lei.",
  },
  {
    id: "anomaly",
    title: "Anomalia",
    means: "Un movimento dell'ultimo mese molto più alto di quelli della sua categoria.",
    computed:
      "Lo confronta con la mediana della categoria, e dice di quante volte la supera. Sotto i 100 € non segnala niente, come per cambi valuta e spese rare.",
    changes: "Una spesa rara non è un'anomalia: segnarla la toglie dall'elenco.",
  },
  {
    id: "sync-limit",
    title: "Limite della banca",
    means:
      "Le banche limitano quante volte al giorno un'app può leggere un conto senza di te. Oltre il limite rifiutano, e quel conto resta fermo all'ultima lettura finché il limite non si azzera: gli altri conti si leggono lo stesso. Riavviare l'app non consuma il limite, premere Sincronizza sì.",
  },
  {
    id: "check",
    title: "Verifica del saldo",
    means:
      "Il controllo che i numeri siano veri: il saldo che dichiara la banca contro quello che risulta qui.",
    computed:
      "Verificato: coincidono. Discrepanza: manca un movimento o ce n'è uno doppio, di solito fra gli ultimi. D'accordo salvo i cancellati: la differenza è esattamente ciò che hai cancellato a mano. Non verificato: nessuno ha dichiarato un saldo, e il silenzio non è un accordo.",
    changes:
      "Ricalcolare il saldo iniziale fa tornare i conti per costruzione: nasconde la differenza invece di spiegarla, e si fa solo sapendo perché. Con Ripristina i cancellati, i movimenti cancellati di un conto tornano al prossimo sync con la loro nota. Il saldo che una banca prevede per una data futura non si verifica e non conta nella liquidità: se è negativo, Conti lo dice come avviso, e il conto non è in rosso. Un saldo di un tipo che l'app non conosce resta fuori allo stesso modo, e Conti lo segnala: non vuol dire che il conto abbia un problema, ma che quel tipo va ancora capito.",
  },
  {
    id: "goal",
    title: "Obiettivo",
    means:
      "Dove vuoi arrivare: un nome, una cifra in euro di oggi, una data, e quanto quel denaro deve restare raggiungibile. Il cuscinetto è liquido in ogni momento, un acquisto deve essere disponibile alla sua data, la pensione può restare vincolata.",
    computed:
      "Un obiettivo vale da una data in poi. Cambiarlo non riscrive il passato: dalla data scelta vale la versione nuova, e prima resta quella vecchia, come il default di un budget. Togliere un obiettivo lo fa smettere di valere da oggi.",
    changes:
      "La data dà l'orizzonte del confronto fra fondo e PAC, e la liquidità dice se il fondo conta: per un obiettivo che non può restare vincolato il fondo non è raggiungibile prima della pensione, salvo le anticipazioni.",
  },
  {
    id: "contribution-base",
    title: "Base del versamento",
    means:
      "La cifra su cui il contratto calcola il versamento al fondo pensione, tuo e del datore. Non è il lordo: nelle buste paga del 2025 e del 2026 la base è rimasta ferma quando a luglio 2026 il lordo è salito.",
    computed:
      "Si scrive a parte nel Profilo, annua, con la data da cui vale. Il datore versa la sua percentuale della base solo se tu versi almeno la tua: sotto quella soglia il confronto lo segna come perso. Il lordo per le mensilità serve invece a trovare l'aliquota a cui si deduce.",
    changes:
      "Una base sbagliata sposta il contributo del datore, e con lui lo spazio che resta sotto il tetto di deducibilità.",
  },
  {
    id: "deduction-cap",
    title: "Tetto di deducibilità",
    means:
      "Quanto si può versare al fondo pensione in un anno togliendolo dal reddito su cui si pagano le tasse: 5.300 € dal 2026. Dentro c'è il contributo del datore, non il TFR.",
    computed:
      "Il dedotto è quanto versi, fino al tetto meno il contributo del datore. Il risparmio d'imposta è l'IRPEF con le addizionali sul reddito meno quella sul reddito dedotto, sugli scaglioni dell'anno; le detrazioni non entrano. Nel confronto finisce nel PAC lo stesso anno. Il fondo paga ogni anno l'imposta sui rendimenti e all'uscita un'aliquota dal 15%, che scende di 0,30 punti per ogni anno di adesione oltre il quindicesimo fino al 9%, solo su quanto è stato dedotto, tuo e del datore, mai oltre il tetto. Il PAC paga il bollo ogni anno e il 26% sul guadagno a scadenza. I parametri si scrivono a mano per anno con la loro fonte, e ogni cifra dice l'anno che ha usato: un anno che manca non si copre con quello prima. Un parametro salvato vuoto si toglie, e il suo anno torna incompleto.",
    changes:
      "Oltre il tetto un euro al fondo non si deduce più, e il confronto cambia: lo spazio sotto il tetto diventa negativo. Il rendimento è uno solo, scritto da te e uguale per fondo e PAC, così la differenza fra le due ripartizioni è quella fiscale; quale scegliere lo decidi tu.",
  },
  {
    id: "scenario",
    title: "Scenario",
    means:
      "Un'ipotesi di rendimento per l'obiettivo: prudente, centrale e favorevole, ognuno con un rendimento reale e un'inflazione all'anno che scrivi tu. Non sono previsioni: sono tre modi di leggere la stessa strada, e quando divergono molto è quella distanza la cosa da guardare.",
    computed:
      "Ogni mese il capitale cresce del rendimento e riceve il versamento: W(t+1) = W(t)·(1 + r) + c, con r il rendimento mensile che in dodici mesi fa quello annuo. Il rendimento è reale, cioè già tolta l'inflazione, quindi tutto è in euro di oggi; l'inflazione serve solo a dire quanto vale la cifra dell'obiettivo in euro della sua data. Il versamento è quello che scrivi, o quello che il ledger mostra: la media mensile dei soldi mandati su Investimenti negli ultimi 12 mesi completi, senza gli aggiornamenti di liquidità del broker. Il capitale già messo da parte lo scrivi tu, finché il portafoglio non è nell'app.",
    changes:
      "La proiezione dice se l'obiettivo si raggiunge a quel ritmo, quanto manca alla data e quanto servirebbe al mese. Gli scenari non si stimano dal passato e uno non scritto si dice invece di sostituirlo: finché non ci sono tutti e tre, la proiezione non parte.",
  },
  {
    id: "coast-fi",
    title: "Coast FI",
    means:
      "Il capitale che, senza altri versamenti, cresce da solo fino alla cifra dell'obiettivo alla sua data. Superarlo vuol dire che il resto del risparmio è libero: l'obiettivo si raggiunge comunque, nello scenario scelto.",
    computed:
      "È la cifra dell'obiettivo divisa per la crescita di quello scenario fino alla data: C = obiettivo / (1 + r)^mesi. Si legge solo per un obiettivo che può restare vincolato, come la pensione, e la cifra dell'obiettivo è il capitale da raggiungere: non c'è un tasso di prelievo.",
    changes:
      "Cambia con lo scenario: nel prudente la soglia è più alta, nel favorevole più bassa. La distanza fra le due dice quanto la soglia dipende dall'ipotesi.",
  },
  {
    id: "withheld",
    title: "Trattenuto e investito",
    means:
      "Un contributo al fondo pensione nasce trattenuto: la busta paga dice quanto è stato tolto, ma il fondo lo riceve dopo, a blocchi irregolari anche di mesi. Diventa investito quando il prospetto lo mostra con la data di valorizzazione, il valore quota e le quote assegnate. Quello che sta in mezzo è in transito.",
    computed:
      "In ogni data trattenuto = investito + in transito, e il transito è quanto il datore ha trattenuto senza averlo ancora versato. Un contributo in transito vale il suo costo. Il prospetto non corrisponde riga per riga alle buste paga: un'operazione investe le buste paga consecutive che sommano esattamente al suo importo, in ordine, e una che non quadra con nessuna si segnala senza forzarla. Un versamento fatto direttamente al fondo nasce investito, con la sua data.",
    changes:
      "Nessuna differenza si corregge da sola: la riconciliazione mostra le due cifre e lo scarto, e la scelta di cosa farne è tua. Il valore quota si legge una volta al mese dalla pagina pubblica della classe del fondo su Borsa Italiana; se la pagina non risponde, è di un'altra classe o dà un altro mese, il Portafoglio chiede di scriverlo a mano, e un mese non prende mai il valore di un altro. Le buste paga e i prospetti arrivano da Paperless: ognuno si legge una volta sola, e su Paperless prende il tag amonhen:importato o amonhen:errore con le cifre lette.",
  },
  {
    id: "opening",
    title: "Apertura",
    means:
      "Quello che un ETF o il fondo teneva in una data, dichiarato una volta sola finché i documenti non arrivano: le quote, il prezzo o il valore quota di quel giorno e quanto avevi versato fino a lì. È un ponte verso i documenti, non un'alternativa.",
    computed:
      "Dopo la data dell'apertura i documenti si sommano a lei; quelli datati fino a quella data sono già dentro, quindi non si sommano ma si riconciliano: la riga «Apertura contro i documenti» mette le quote dichiarate accanto a quelle che i documenti spiegano. Per il fondo conta la data della busta paga, e le quote di un contributo investito dopo l'apertura si aggiungono, perché quel giorno era in transito. Prima dell'apertura lo strumento non tiene niente, e i rendimenti partono dal suo valore di quel giorno.",
    changes:
      "Quando i documenti spiegano tutta l'apertura la riga lo dice, e l'apertura si ritira: da lì valgono solo i documenti e i rendimenti partono dal primo versamento. Il BTP non ne ha bisogno, i suoi termini bastano.",
  },
  {
    id: "twr",
    title: "TWR",
    means:
      "Il rendimento dello strumento, indipendente da quanto e quando versi: il prodotto della crescita fra un flusso e il successivo. Dice come è andato l'ETF o il fondo, non come sei andato tu.",
    computed:
      "Il valore prima di ogni versamento si prende al prezzo di quella transazione, quindi non serve uno storico dei prezzi oltre quello di fine mese. Per l'insieme degli strumenti si concatenano i mesi: il valore di fine mese, tolti i versamenti di quel mese, contro quello del mese prima, con i flussi contati a fine mese. Un BTP e la casa non hanno un prezzo di mercato che entri, e il loro TWR non c'è.",
    changes:
      "Cambia con i prezzi e non con le date dei versamenti: due persone che hanno comprato lo stesso ETF in momenti diversi hanno lo stesso TWR e MWR diversi.",
  },
  {
    id: "mwr",
    title: "MWR",
    means:
      "Il rendimento tuo: il tasso annuo costante che, applicato ai versamenti nelle date in cui li hai fatti, porta al valore di oggi. Dipende dal momento dei versamenti, ed è il solo che si può leggere per l'insieme di ETF, fondo e BTP.",
    computed:
      "È la radice di Σ flusso × (1 + r)^(-anni) = 0, con il valore di oggi come ultimo flusso, cercata fra due estremi che la contengono. Per il fondo i versamenti contano alla data della busta paga, quindi i mesi in transito costano rendimento. Il BTP conta con il nominale all'acquisto, le cedole nette incassate e il nominale più rateo di oggi.",
    changes:
      "Se i flussi non hanno una radice, per esempio c'è solo un versamento e niente valore, la cifra non c'è e non si inventa.",
  },
  {
    id: "accrual",
    title: "Rateo",
    means:
      "La parte della cedola in corso che il BTP ha già maturato: tenuto fino a scadenza il suo prezzo torna a 100, quindi il titolo vale il nominale più il rateo.",
    computed:
      "È la cedola netta del trimestre, proporzionale ai giorni passati dall'ultima cedola. Le cedole sono trimestrali, nette dell'imposta, con il tasso del periodo (4,10% i primi tre anni, 4,50% gli ultimi due, scritto fra i termini del titolo). Il premio fedeltà non entra mai nel rateo: vale solo alla scadenza, perché spetta solo a chi ci arriva.",
    changes:
      "Dopo una cedola il rateo riparte da zero e il versato netto, cioè il nominale meno le cedole incassate, scende.",
  },
  {
    id: "service",
    title: "Servizio e sessione",
    means:
      "Un servizio a prezzo concordato, dato o ricevuto: lezioni private, lezioni prese, sedute. Ogni sessione è un evento sul calendario Google con il titolo del servizio, e i pagamenti sono i movimenti del ledger collegati al servizio.",
    computed:
      "Le sessioni le scrive il calendario: un evento il cui titolo contiene quello del servizio (maiuscole e spazi a parte), o che corrisponde a un'espressione fra barre, diventa una sessione al prezzo del servizio. Ogni lettura chiede al calendario i 90 giorni prima e i 90 dopo oggi, e la sezione dice il periodo letto. Un evento cancellato o rinominato la rende annullata. I pagamenti si collegano da soli quando il movimento porta l'IBAN della controparte, nel verso del servizio; gli altri si cercano dalla sezione, per controparte, descrizione o importo.",
    changes:
      "Cambiare il prezzo vale per le sessioni nuove: quelle già scritte tengono il loro importo, che si corregge una per una. Un servizio non entra in nessuna cifra di spesa: il movimento tiene la sua categoria.",
  },
  {
    id: "coverage",
    title: "Saldo e copertura",
    means:
      "Il saldo è quanto resta: le sessioni valide fino a oggi meno i pagamenti collegati. Positivo vuol dire che la controparte deve ancora pagare, o che devi ancora pagare tu per un servizio ricevuto; negativo, che è stato pagato in anticipo.",
    computed:
      "I pagamenti coprono le sessioni in ordine di data, dalla più vecchia: una sessione è pagata, in parte o da pagare a seconda di dove arriva la somma dei pagamenti. Non è scritto da nessuna parte, si ricalcola ogni volta. Una sessione futura non conta finché la sua data non arriva.",
    changes:
      "Correggere un importo, annullare una sessione o collegare un pagamento sposta la copertura di tutte le sessioni dopo, ma non quella di prima.",
  },
];

/** The concepts, one card each: the only place the pages explain anything. */
export function GuideScreen({ topic }: { topic: GuideTopic | null }) {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const chosen = useRef<HTMLDetailsElement>(null);

  // The figures are examples: without them the cards still say all they say.
  useEffect(() => {
    const controller = new AbortController();
    const { from, to } = monthBounds(currentMonth());
    api
      .metrics({ from, to, accounts: [], categories: [], tags: [] }, controller.signal)
      .then(setMetrics)
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  useEffect(() => {
    chosen.current?.scrollIntoView({ block: "center" });
  }, [topic]);

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Guida</h1>
        </div>
      </header>

      <ul className="card-list">
        {CARDS.map((card) => {
          const now = metrics === null ? null : (card.now?.(metrics) ?? null);
          return (
            <li key={card.id}>
              <details
                className="guide"
                open={card.id === topic ? true : undefined}
                ref={card.id === topic ? chosen : undefined}
              >
                <summary className="guide__title">
                  <span>{card.title}</span>
                  {now === null ? null : <span className="guide__now">{now}</span>}
                </summary>
                <p>{card.means}</p>
                {card.computed ? <p>{card.computed}</p> : null}
                {card.changes ? <p>{card.changes}</p> : null}
              </details>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
