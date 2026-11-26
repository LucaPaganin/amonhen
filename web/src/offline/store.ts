// The phone's own storage for the copy: one IndexedDB store of keys and values. A value
// is the whole thing at once (the bundle, the queue, the snapshots), so a write is
// all-or-nothing and nothing here knows what it holds.
const DATABASE = "amonhen-offline";
const STORE = "kv";

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function run<T>(mode: IDBTransactionMode, work: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const database = await open();
  try {
    return await new Promise<T>((resolve, reject) => {
      const transaction = database.transaction(STORE, mode);
      const request = work(transaction.objectStore(STORE));
      transaction.oncomplete = () => resolve(request.result);
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  } finally {
    database.close();
  }
}

export const read = <T>(key: string): Promise<T | undefined> =>
  run("readonly", (store) => store.get(key) as IDBRequest<T | undefined>);

export const write = (key: string, value: unknown): Promise<unknown> =>
  run("readwrite", (store) => store.put(value, key));

export const remove = (key: string): Promise<undefined> =>
  run("readwrite", (store) => store.delete(key));

/**
 * Ask the browser not to clear the copy when it needs room: a queue of changes that has
 * not been sent is the one thing here that cannot be downloaded again. The answer is
 * the browser's, and a refusal is only said, never worked around.
 */
export async function requestPersistence(): Promise<boolean> {
  try {
    return (await navigator.storage?.persist?.()) ?? false;
  } catch {
    return false;
  }
}
