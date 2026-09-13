/**
 * The review bucket has two lives. It is a key: a rule may not point at it,
 * the API filters on its name, the ledger stores it as the category account the
 * unclassified postings sit on. And it is a word somebody reads, in a chip, in
 * a filter, in the legend of the pie.
 *
 * Only the second life is translated here. Every value the app sends back is
 * still the name the server gave it, and the name itself is a setting
 * (`AMONHEN_UNCATEGORIZED`), so it is learned at boot instead of assumed.
 */
let bucket = "Uncategorized";

/** Learn the name the server uses, once, from its handshake. */
export function rememberBucket(name: string | undefined): void {
  if (name) bucket = name;
}

/**
 * The name a rule may not point at and the one the app must never offer as a
 * choice, as opposed to what to show a person in its place.
 */
export function bucketName(): string {
  return bucket;
}

/** What to show where a category name is read. */
export function categoryText(name: string | null | undefined): string {
  if (!name) return "Senza categoria";
  return name === bucket ? "Senza categoria" : name;
}
