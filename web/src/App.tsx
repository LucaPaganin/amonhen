import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "./api";
import { rememberBucket } from "./category";
import { Navigation, TabBar } from "./components/Navigation";
import type { TabId } from "./components/Navigation";
import { Toast } from "./components/Toast";
import { AccountsScreen } from "./screens/Accounts";
import { AssistantScreen } from "./screens/Assistant";
import { DashboardScreen } from "./screens/Dashboard";
import { MovementsScreen } from "./screens/Movements";
import { ReviewQueueScreen } from "./screens/ReviewQueue";
import { CategoryRulesScreen } from "./screens/CategoryRules";
import { syncSummary } from "./notices";
import type { AssistantContext } from "./types";
import { useCategories } from "./useCategories";
import { useReviewQueue } from "./useReviewQueue";
import { useRules } from "./useRules";

/**
 * The API shape this bundle reads. Keep in step with `API_VERSION` in
 * `amonhen/api.py`: the bundle is served from disk on every request
 * while the Python process can still be running older code, and a missing key
 * used to take the whole screen down with it.
 */
const REQUIRED_API_VERSION = 17;

export default function App() {
  const [tab, setTab] = useState<TabId>("dashboard");
  const [staleServer, setStaleServer] = useState(false);
  // What the assistant was opened from, when it was opened from a screen: the
  // question is born there, and the section is handed the thing it is about.
  const [assistantContext, setAssistantContext] = useState<AssistantContext | null>(null);
  // A sync writes movements underneath every screen, so a number that counts
  // them is bumped and the screens that read the ledger fetch again. A key that
  // only grows, rather than a remount: a filter a person chose survives it.
  const [syncedAt, setSyncedAt] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [syncNotice, setSyncNotice] = useState<string | null>(null);
  const review = useReviewQueue();
  const {
    categories,
    error: categoriesError,
    reload: reloadCategories,
    updateCategoryFlags,
  } = useCategories();
  // Writing a rule changes what the queue has left to decide, so refresh it.
  const rules = useRules(review.reload);
  const reviewCount = review.proposalsTotal + review.transfersTotal;

  useEffect(() => {
    const controller = new AbortController();
    api
      .health(controller.signal)
      .then((health) => {
        // A failed check is not a verdict: the screens report their own errors.
        if ((health.api_version ?? 0) < REQUIRED_API_VERSION) setStaleServer(true);
        rememberBucket(health.uncategorized);
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  // Accepting a proposal writes a rule without going through the section, so
  // opening it refetches instead of showing a list from minutes ago. The
  // categories go with it: a category can be created from the queue too.
  useEffect(() => {
    if (tab === "categories") {
      rules.reload();
      reloadCategories();
    }
  }, [tab, rules.reload, reloadCategories]);

  const openAssistant = useCallback((context: AssistantContext) => {
    setAssistantContext(context);
    setTab("assistant");
  }, []);
  const clearAssistantContext = useCallback(() => setAssistantContext(null), []);
  const dismissSyncNotice = useCallback(() => setSyncNotice(null), []);

  // The server does the work and the answer is the summary; the screens are
  // told to read the ledger again rather than left showing what they had.
  const runSync = useCallback(async () => {
    setSyncing(true);
    setSyncNotice(null);
    try {
      const outcome = await api.sync();
      setSyncNotice(syncSummary(outcome));
      setSyncedAt((count) => count + 1);
      review.reload();
      reloadCategories();
    } catch (error) {
      setSyncNotice(`Sync non riuscito: ${errorMessage(error)}`);
    } finally {
      setSyncing(false);
    }
  }, [reloadCategories, review]);

  if (staleServer) {
    return (
      <div className="app">
        <main className="app__main app__main--plain">
          <section className="screen">
            <header className="screen__header">
              <div>
                <h1 className="screen__title">Server non aggiornato</h1>
              </div>
            </header>
            <div className="state state--error" role="alert">
              <p>
                Questa app è più recente del server che la serve: l&apos;API risponde con un
                formato vecchio e le schermate non lo sanno leggere.
              </p>
              <p>Riavvia il servizio per allinearlo:</p>
              <pre className="state__command">uv run python -m amonhen serve</pre>
              <p>
                Se gira in un container, ricostruisci l&apos;immagine: il codice Python non si
                aggiorna da solo, mentre il bundle viene letto dal disco a ogni richiesta.
              </p>
            </div>
          </section>
        </main>
      </div>
    );
  }

  return (
    <div className="app">
      <Navigation
        active={tab}
        reviewCount={reviewCount}
        onChange={setTab}
        syncing={syncing}
        onSync={() => void runSync()}
      />

      <main className="app__main">
        {tab === "review" ? (
          <ReviewQueueScreen
            review={review}
            categories={categories}
            categoriesError={categoriesError}
            onReloadCategories={reloadCategories}
          />
        ) : null}
        {tab === "movements" ? (
          <MovementsScreen
            categories={categories}
            categoriesError={categoriesError}
            onReloadCategories={reloadCategories}
            onCategorize={review.categorize}
            onReviewReload={review.reload}
            refreshToken={syncedAt}
          />
        ) : null}
        {tab === "dashboard" ? (
          <DashboardScreen categories={categories} refreshToken={syncedAt} />
        ) : null}
        {tab === "accounts" ? (
          <AccountsScreen onAskAssistant={openAssistant} refreshToken={syncedAt} />
        ) : null}
        {tab === "assistant" ? (
          <AssistantScreen
            context={assistantContext}
            onContextUsed={clearAssistantContext}
          />
        ) : null}
        {tab === "categories" ? (
          <CategoryRulesScreen
            rules={rules}
            categories={categories}
            categoriesError={categoriesError}
            onReloadCategories={reloadCategories}
            updateCategoryFlags={updateCategoryFlags}
          />
        ) : null}
        <p className="app__epigraph">
          “The Eye of Sauron the Terrible few could endure” — J.R.R. Tolkien, Il Silmarillion
        </p>
      </main>

      <TabBar active={tab} reviewCount={reviewCount} onChange={setTab} />

      {syncNotice !== null ? (
        <Toast message={syncNotice} onDismiss={dismissSyncNotice} />
      ) : review.notice ? (
        <Toast message={review.notice} onDismiss={review.dismissNotice} />
      ) : null}
    </div>
  );
}
