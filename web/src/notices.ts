import type { Deletion, SyncAccountResult, SyncOutcome } from "./types";

/**
 * What the toast says after a sync.
 *
 * The button asks one question — what is new — and the answer has to be
 * readable in one line per account: what arrived, or why that account could
 * not be read. The overlap the sync re-reads on purpose is not news, so the
 * duplicates it produces are left out; a count of zero is not shown.
 */
export function syncSummary(outcome: SyncOutcome): string {
  if (outcome.accounts.length === 0) return "Nessun conto da sincronizzare in accounts.json.";

  // A movement a person deleted is a thing the sync saw and left alone: the
  // button that asked for this run has to say so, or the count would look
  // wrong for no visible reason.
  const suppressed = outcome.accounts.reduce(
    (total, account) => total + (account.actions.suppressed ?? 0),
    0,
  );
  const extras = [
    outcome.transfers_linked === 0
      ? null
      : `${outcome.transfers_linked} ${
          outcome.transfers_linked === 1 ? "giroconto collegato" : "giroconti collegati"
        }`,
    outcome.rules_applied === 0 ? null : `${outcome.rules_applied} categorizzati dalle regole`,
    outcome.passthrough_legs === 0
      ? null
      : `${outcome.passthrough_legs} verso un conto dichiarato`,
    suppressed === 0 ? null : `${suppressed} cancellati a mano, lasciati fuori`,
  ].filter((extra): extra is string => extra !== null);

  return [...outcome.accounts.map(accountLine), ...extras].join(" · ");
}

function accountLine(account: SyncAccountResult): string {
  if (account.error !== null) return `${account.account}: ${account.error}`;

  const inserted = account.actions.inserted ?? 0;
  const promoted = account.actions.promoted ?? 0;
  const reimported = account.actions.reimported ?? 0;
  const news = [
    inserted === 0 ? null : `${inserted} ${inserted === 1 ? "nuovo" : "nuovi"}`,
    promoted === 0 ? null : `${promoted} ${promoted === 1 ? "aggiornato" : "aggiornati"}`,
    reimported === 0 ? null : `${reimported} riportati dal cestino`,
  ].filter((part): part is string => part !== null);

  if (news.length === 0) {
    return `${account.account}: nessun movimento nuovo (${account.fetched} riletti)`;
  }
  // A sync that writes movements can also be the moment the invariant breaks:
  // "è arrivato questo" and "e ora non torna" are both part of the answer.
  const mismatch = account.balance_mismatch === null ? "" : " · saldo non riconciliato";
  return `${account.account}: ${news.join(", ")}${mismatch}`;
}

/**
 * What the app says after a movement leaves the ledger.
 *
 * It does not promise the sync will leave it alone: an account whose
 * `reimport_deleted` flag is on brings its deleted movements back at the next
 * run, and that flag is a decision made in Conti, not a sentence this screen
 * can speak for.
 */
export function deletionNotice(deleted: Deletion): string {
  return deleted.unlinked_pair
    ? "Movimento cancellato: il giroconto è stato annullato e l'altra gamba è tornata in coda"
    : "Movimento cancellato: è nel cestino del conto, in Conti";
}
