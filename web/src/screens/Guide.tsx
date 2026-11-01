import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { api } from "../api";
import { currentMonth, formatAmount, formatMonths } from "../format";
import type { Metrics } from "../types";

export type GuideTopic =
  | "month"
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
  | "sync-limit";

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
      "Quanto è uscito finora in questo mese, senza le spese rare, contro quanto esce di solito a questo punto del mese.",
    computed:
      "Il solito è la mediana dei 6 mesi completi precedenti, ciascuno tagliato allo stesso giorno, per il totale e per ogni categoria. Sono mediane separate: i soliti delle categorie non sommano al solito del totale. I contributi alle spese stanno fuori dal confronto, che così non dipende dal giorno in cui arrivano: hanno una riga loro, con quanto resta a tuo carico.",
    changes:
      "Dove sono finiti elenca le categorie con una spesa in questo mese, dalla più alta, ognuna con la sua distanza dal solito. Un tocco apre i suoi movimenti.",
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
      "Un accredito in una categoria col segno Contributo alle spese abbassa il totale e nessuna categoria. Copre tutte le spese del conto su cui arriva, rare comprese: in ogni mese tutto ciò che quel conto ha pagato scende della stessa percentuale, e gli altri conti restano interi. Riduce spesa tipica, riserva per spese rare e spesa attesa, quindi allunga i mesi di autonomia. Questo mese e Dove sono finiti restano lordi.",
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
      "Due movimenti di pari importo e segno opposto su conti diversi, a non più di due giorni, vengono proposti in Da confermare. Il nome del conto stampato dalla banca conferma la coppia.",
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
];

/** The concepts, one card each: the only place the pages explain anything. */
export function GuideScreen({ topic }: { topic: GuideTopic | null }) {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const chosen = useRef<HTMLDetailsElement>(null);

  // The figures are examples: without them the cards still say all they say.
  useEffect(() => {
    const controller = new AbortController();
    const month = currentMonth();
    api
      .metrics({ from: month, to: month, accounts: [], categories: [], tags: [] }, controller.signal)
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
