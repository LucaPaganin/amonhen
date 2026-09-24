import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";

export type TabId =
  | "dashboard"
  | "review"
  | "movements"
  | "accounts"
  | "categories"
  | "assistant";

interface Section {
  id: TabId;
  /** The full name: what a screen calls itself, and what a screen reader hears. */
  label: string;
  /** What fits in one of the bar's columns, which are five. */
  short: string;
  /** What the section holds, in the room a drawer has and the bar does not. */
  hint: string;
  /** In the bottom bar, or only in the menu: six labels do not fit five columns. */
  inBar: boolean;
  Icon: () => ReactElement;
}

const SECTIONS: Section[] = [
  {
    id: "dashboard",
    label: "Dashboard",
    short: "Dashboard",
    hint: "Spese, entrate e patrimonio",
    inBar: true,
    Icon: ChartIcon,
  },
  {
    id: "review",
    label: "Da confermare",
    short: "Da confermare",
    hint: "Cosa aspetta una decisione",
    inBar: true,
    Icon: ClipboardIcon,
  },
  {
    id: "movements",
    label: "Movimenti",
    short: "Movimenti",
    hint: "Un mese di movimenti per volta",
    inBar: true,
    Icon: ListIcon,
  },
  {
    id: "accounts",
    label: "Conti e budget",
    short: "Conti",
    hint: "Saldi, budget e categorie",
    inBar: true,
    Icon: WalletIcon,
  },
  {
    id: "categories",
    label: "Categorie e regole",
    short: "Categorie",
    hint: "Le categorie, i loro flag e cosa ci finisce",
    inBar: true,
    Icon: RulesIcon,
  },
  {
    id: "assistant",
    label: "Assistente",
    short: "Assistente",
    hint: "Una lettura dei numeri già calcolati",
    inBar: false,
    Icon: AssistantIcon,
  },
];

interface SectionNavProps {
  active: TabId;
  reviewCount: number;
  onChange: (tab: TabId) => void;
}

interface NavProps extends SectionNavProps {
  /** A sync in flight: the button says so and refuses a second tap. */
  syncing: boolean;
  /** Asks the server for data now; the answer arrives as a toast. */
  onSync: () => void;
}

function menuLabel(section: Section, reviewCount: number): string {
  if (section.id === "review" && reviewCount > 0) {
    return `${section.label}: ${reviewCount} da gestire`;
  }
  return section.label;
}

function AssistantIcon() {
  return (
    <svg
      className="navicon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M4 5.5h16v10H9l-5 4z" />
      <path d="M8.5 10.5h.01M12 10.5h.01M15.5 10.5h.01" />
    </svg>
  );
}

function ClipboardIcon() {
  return (
    <svg
      className="navicon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M9 4h6a1 1 0 0 1 1 1v1H8V5a1 1 0 0 1 1-1Z" />
      <path d="M16 5h2a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h2" />
      <path d="m9 13 2 2 4-4" />
    </svg>
  );
}

function ListIcon() {
  return (
    <svg
      className="navicon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M4 7h16M4 12h16M4 17h10" />
    </svg>
  );
}

function ChartIcon() {
  return (
    <svg
      className="navicon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M4 20V4" />
      <path d="M4 20h16" />
      <path d="M8 16v-5M12.5 16V7M17 16v-3" />
    </svg>
  );
}

function WalletIcon() {
  return (
    <svg
      className="navicon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M4 8a2 2 0 0 1 2-2h11a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8Z" />
      <path d="M4 10h16" />
      <path d="M15 14h2" />
    </svg>
  );
}

function RulesIcon() {
  return (
    <svg
      className="navicon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M10 6h10M10 12h10M10 18h10" />
      <path d="m3 6 1.5 1.5L7 5M3 12l1.5 1.5L7 11M3 18l1.5 1.5L7 17" />
    </svg>
  );
}

function BarsIcon() {
  return (
    <svg
      className="navicon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      className="navicon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  );
}

/**
 * The hamburger, and the drawer it opens.
 *
 * The bottom bar switches sections in one tap, which is what a phone is for, but
 * five columns leave room for one word each. The drawer is the other half: it
 * names the sections in full and says what is inside them, so a section you have
 * not opened before is not a guess. Both paths call the same `onChange`, and the
 * sections themselves are declared once above.
 *
 * The bar also carries the one control that is not a section: asking Enable
 * Banking for the data now, instead of waiting for the scheduled pass.
 */
export function Navigation({ active, reviewCount, onChange, syncing, onSync }: NavProps) {
  const [open, setOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    // Focus lands inside the drawer, so a keyboard or a screen reader walks the
    // sections instead of the screen behind them; Escape closes it.
    panel.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close(true);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  function close(returnFocus = false) {
    setOpen(false);
    if (returnFocus) menuButton.current?.focus();
  }

  return (
    <>
      <header className="appbar">
        <div className="appbar__inner">
          <button
            ref={menuButton}
            type="button"
            className="appbar__menu"
            aria-label="Sezioni"
            aria-expanded={open}
            aria-controls="nav-drawer"
            onClick={() => setOpen(true)}
          >
            <BarsIcon />
          </button>
          <span className="appbar__brand">AmonHen</span>
          <button
            type="button"
            className="button appbar__sync"
            onClick={onSync}
            disabled={syncing}
            aria-busy={syncing}
          >
            {syncing ? "Sincronizzo…" : "Sincronizza"}
          </button>
        </div>
      </header>

      <div className={open ? "drawer drawer--open" : "drawer"}>
        <div className="drawer__backdrop" onClick={() => close(true)} />
        <div
          id="nav-drawer"
          ref={panel}
          className="drawer__panel"
          role="dialog"
          aria-modal="true"
          aria-label="Sezioni"
          /* Shut, the panel is off-screen and inert: nothing in it takes a tap or a
             tab stop, and focus can land in it the moment it opens. */
          inert={!open}
          tabIndex={-1}
        >
          <div className="drawer__head">
            <p className="drawer__title">Sezioni</p>
            <button
              type="button"
              className="drawer__close"
              aria-label="Chiudi il menu"
              onClick={() => close(true)}
            >
              <CloseIcon />
            </button>
          </div>
          <ul className="drawer__list">
            {SECTIONS.map((section) => (
              <li key={section.id}>
                <button
                  type="button"
                  className="drawer__item"
                  aria-current={active === section.id ? "page" : undefined}
                  aria-label={menuLabel(section, reviewCount)}
                  onClick={() => {
                    onChange(section.id);
                    close(true);
                  }}
                >
                  <section.Icon />
                  <span className="drawer__text">
                    <span className="drawer__label">{section.label}</span>
                    <span className="drawer__hint">{section.hint}</span>
                  </span>
                  {section.id === "review" && reviewCount > 0 ? (
                    <span className="drawer__count" aria-hidden="true">
                      {reviewCount}
                    </span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  );
}

export function TabBar({ active, reviewCount, onChange }: SectionNavProps) {
  return (
    <nav className="tabbar" aria-label="Sezioni">
      {SECTIONS.filter((section) => section.inBar).map((section) => (
        <button
          key={section.id}
          type="button"
          className="tabbar__item"
          aria-current={active === section.id ? "page" : undefined}
          aria-label={menuLabel(section, reviewCount)}
          onClick={() => onChange(section.id)}
        >
          <section.Icon />
          <span className="tabbar__label">{section.short}</span>
          {section.id === "review" && reviewCount > 0 ? (
            <span className="tabbar__badge" aria-hidden="true">
              {reviewCount}
            </span>
          ) : null}
        </button>
      ))}
    </nav>
  );
}
