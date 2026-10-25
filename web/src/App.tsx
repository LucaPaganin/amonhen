import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "./api";
import { rememberBucket } from "./category";
import { Epigraph } from "./components/Epigraph";
import { Navigation, TabBar } from "./components/Navigation";
import type { TabId } from "./components/Navigation";
import { Toast } from "./components/Toast";
import { AccountsScreen } from "./screens/Accounts";
import { BudgetScreen } from "./screens/Budget";
import { AssistantScreen } from "./screens/Assistant";
import { DashboardScreen } from "./screens/Dashboard";
import { MovementsScreen } from "./screens/Movements";
import { ImportScreen } from "./screens/Import";
import { ReviewQueueScreen } from "./screens/ReviewQueue";
import { CategoryRulesScreen } from "./screens/CategoryRules";
import { SetupScreen, setupStartStep } from "./screens/Setup";
import { syncSummary } from "./notices";
import type { AssistantContext } from "./types";
import { useCategories } from "./useCategories";
import { useReviewQueue } from "./useReviewQueue";
import { useRules } from "./useRules";
import { useSetup } from "./useSetup";

/**
 * The API shape this bundle reads. Keep in step with `API_VERSION` in
 * `amonhen/api.py`: the bundle is served from disk on every request
 * while the Python process can still be running older code, and a missing key
 * used to take the whole screen down with it.
 */
const REQUIRED_API_VERSION = 23;

export default function App() {
  // `?setup=1` is where the bank sends the browser back after a login, and the
  // wizard is what it came back for. It is the starting section, so leaving the
  // wizard is a normal section change.
  const [tab, setTab] = useState<TabId>(() => (hasSetupParam() ? "setup" : "dashboard"));
  const [staleServer, setStaleServer] = useState(false);
  // What the assistant was opened from, when it was opened from a screen: the
  // question is composed there, and the section is handed the thing it is about.
  // The section asks it only when a button is pressed, so this survives until
  // the person asks it or drops it.
  const [assistantContext, setAssistantContext] = useState<AssistantContext | null>(null);
  // A sync writes movements underneath every screen, so a number that counts
  // them is bumped and the screens that read the ledger fetch again. A key that
  // only grows, rather than a remount: a filter a person chose survives it.
  const [syncedAt, setSyncedAt] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [syncNotice, setSyncNotice] = useState<string | null>(null);
  const setup = useSetup();
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

  // A configuration that does not exist yet leaves nothing to put behind the
  // wizard, so the wizard is the app. The answer is read where it is used — a
  // commit that sees `configured: false` never draws the shell first — and the
  // latch keeps it that way: the setup steps write the very file this asks
  // about, and the wizard must not be swapped for a shell halfway through.
  const [wizardLatched, setWizardLatched] = useState(false);
  const wizardOwnsTheApp =
    wizardLatched || (setup.state !== null && !setup.state.configured);
  useEffect(() => {
    if (setup.state !== null && !setup.state.configured) setWizardLatched(true);
  }, [setup.state]);

  const closeWizard = useCallback(() => {
    // `?setup=1` was the bank's return address, and it has been answered: it
    // leaves the URL here so a reload does not reopen what has been finished.
    dropSetupParam();
    setWizardLatched(false);
    setTab("dashboard");
  }, []);

  const changeTab = useCallback((next: TabId) => {
    setTab(next);
    // Any other section is a way out of the wizard, and a way out drops the
    // parameter: it was an instruction for the boot, not a place.
    if (next !== "setup") dropSetupParam();
  }, []);

  // The wizard writes configuration and movements, so the screens that count
  // what it wrote read again rather than showing what they had before it.
  const noteWrote = useCallback(() => {
    setSyncedAt((count) => count + 1);
    review.reload();
    reloadCategories();
  }, [reloadCategories, review]);

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

  // Until the setup answer arrives there is no telling whether the app or the
  // wizard is the thing to draw, and a configured install must not flash a
  // wizard it is never going to show.
  if (setup.state === null && setup.error === null) {
    return (
      <div className="app">
        <main className="app__main app__main--plain">
          <p className="state" aria-busy="true">
            Caricamento…
          </p>
        </main>
      </div>
    );
  }

  // The wizard is the whole app while the configuration does not exist: there
  // is nothing behind it that could work, and nothing to reach it from.
  if (wizardOwnsTheApp) {
    return (
      <div className="app">
        <main className="app__main app__main--plain">
          <SetupScreen
            setup={setup}
            initialStep={setup.state === null ? 0 : setupStartStep(setup.state)}
            onWrote={noteWrote}
            onClose={closeWizard}
          />
        </main>
      </div>
    );
  }

  // Il wizard è una schermata da fare, non da leggere: la fascia
  // dell'iscrizione resta alle sezioni.
  const showsEpigraph = tab !== "setup";

  return (
    <div className="app">
      <Navigation
        active={tab}
        reviewCount={reviewCount}
        onChange={changeTab}
        syncing={syncing}
        onSync={() => void runSync()}
      />

      <main className="app__main">
        {showsEpigraph ? <Epigraph /> : null}
        {tab === "setup" ? (
          <SetupScreen
            setup={setup}
            initialStep={setup.state === null ? 0 : setupStartStep(setup.state)}
            onWrote={noteWrote}
            onClose={closeWizard}
          />
        ) : null}
        {tab === "review" ? (
          <ReviewQueueScreen
            review={review}
            categories={categories}
            categoriesError={categoriesError}
            onReloadCategories={reloadCategories}
            onSaveRule={rules.add}
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
            onSaveRule={rules.add}
          />
        ) : null}
        {tab === "dashboard" ? (
          <DashboardScreen categories={categories} refreshToken={syncedAt} />
        ) : null}
        {tab === "budget" ? (
          <BudgetScreen onAskAssistant={openAssistant} refreshToken={syncedAt} />
        ) : null}
        {tab === "accounts" ? <AccountsScreen refreshToken={syncedAt} /> : null}
        {tab === "import" ? <ImportScreen onImported={noteWrote} /> : null}
        {tab === "assistant" ? (
          <AssistantScreen
            context={assistantContext}
            onContextDone={clearAssistantContext}
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
      </main>

      <TabBar active={tab} reviewCount={reviewCount} onChange={changeTab} />

      {syncNotice !== null ? (
        <Toast message={syncNotice} onDismiss={dismissSyncNotice} />
      ) : review.notice ? (
        <Toast message={review.notice} onDismiss={review.dismissNotice} />
      ) : null}
    </div>
  );
}

/** `?setup=1` is the address the bank sends the browser back to. */
function hasSetupParam(): boolean {
  return new URLSearchParams(window.location.search).has("setup");
}

/** Drops it, keeping the path: the wizard was a place to be, not an address. */
function dropSetupParam(): void {
  if (window.location.search === "") return;
  window.history.replaceState(null, "", window.location.pathname);
}
