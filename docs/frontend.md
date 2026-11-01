# The PWA

Part of what `CLAUDE.md` says before changing code. A rule that changes changes here, in the same change as the code.

- **The page shows one thing, the Guide explains it.** A row is one strong figure and
  the frequent action; what is rare or dangerous is behind *Dettagli* (the account
  row in Conti) or a tap (a rule's removal is in its sheet). An explanation is not
  written on a page: it is a card in `web/src/screens/Guide.tsx`, reached by the `?`
  (`components/Help.tsx`), and a change to a computation updates that card in the same
  change, like the spec. A section with nothing in it is not drawn, and a label equal
  on every row is not printed.
- **Movimenti shows the everyday by default.** `everyday=true` on
  `/api/transactions` leaves out movements with a virtual posting and everything on a
  `computed_balance` account (transfers and the deposit's daily interest), and
  `hidden` says how many, so the list never looks shorter than the ledger in silence.
- **The release is on screen.** The foot of the drawer and of the rail says
  `AmonHen <bundle>`, and `· server <version>` beside it when the two differ. The
  image gets the tag as the `AMONHEN_VERSION` build-arg (`image.yml`; the build
  context has no `.git`), which becomes `VITE_APP_VERSION` in the bundle and
  `AMONHEN_VERSION` for the server; `settings.VERSION` falls back to `git describe
  --tags --always --dirty` in a checkout, and a bundle built there says `dev`.
- **The document is never cached; the assets always are.** The API serves `index.html`
  with `Cache-Control: no-cache` and `web/public/sw.js` caches only `/assets/*`, whose
  names come from their content. A cached document points at files a rebuild has
  replaced: the page loads a 404 script and comes up blank, which is also the one way
  an update can look like it never happened. `API_VERSION` catches the other
  direction — a stale bundle against a newer server.
- **A colour is named once, in `web/src/styles.css`.** The `:root` block holds the field's
  three glows, the three fill levels, the palette, the type scale, the radii and the two
  motion curves; a component reads a token. Nothing in the interface draws a line: a panel
  is a lighter fill, a control a lighter fill still, and a state is its own colour on a 15%
  tint of it, which is the ceiling — at 22% the money-out red and the transfer violet drop
  below 4.5 against that tint. Text colours are chosen against the lightest patch the glows
  can produce rather than against the base colour. With no outline the boundary of a control
  is its fill, and a subtle fill cannot reach the 3:1 WCAG 1.4.11 asks of a non-text cue, so
  the label inside the control and the brass focus ring are what carry it. The font is a
  Latin-subset Plus Jakarta Sans variable file in `web/src/assets/` rather than
  `web/public/`: Vite emits it into the hashed `/assets/` directory the service worker
  caches, so an offline start does not wait on the network, and the licence file ships beside
  it. Figures stay tabular — a face whose digits are proportional breaks every column of
  amounts. Two surfaces are painted by the browser rather than by the stylesheet, and
  both need care: a `select`'s drop-down is drawn from the control's own colour, so a
  translucent fill there composites over a light ground and yields a white menu with the
  app's near-white text (hence the opaque `--menu`, which the selects carrying
  `class="input"` need the rule to name explicitly, that class being more specific than a
  bare `select`), and a shadow on a filled control must carry no offset, or it reads as a
  smear detached below the button instead of a halo around it. The arrow and, where the
  engine allows it, the menu itself are the stylesheet's: `appearance: none` with a chevron
  image 16 px in from the right edge, and `::picker(select)` — `appearance: base-select`
  has to be declared on the picker as well, or the control alone styles and the menu stays
  the engine's own, square-cornered and highlighted in the platform's blue.
- **The desktop is a layer, not a second layout.** Everything the wide window gets lives in one
  section at the foot of `web/src/styles.css`, above 1024 px (and one step more above 1440), and
  the cap of the content column is the single token `--shell` — read by `.app__main` and the top
  bar (and, below 1024, the bottom bar) because they frame that column, while above 1024 the frame
  is the rail, whose width is its own token and is paid for by `.app`'s
  `padding-left`. Panels that share a row say so where they are written
  (`panel--pair`), and are not guessed from their contents or their
  neighbours: two charts drawn instead of three, or one of two lists missing, is enough to leave
  a panel half-wide beside an empty half. Below the threshold nothing at all may move, and that is
  verified by comparing every element's box at 390 and 768 against the previous build, not by eye.
- **The three shapes of the section list are one list.** `SECTIONS` in
  `web/src/components/Navigation.tsx` draws the rail (above 1024), the bottom bar (below) and the
  drawer — the item's look is declared once (`.navitem`), and the bar keeps the compact variant
  because a column 70 px wide has room for one short word and a wrap, not for a full name. Above
  1024 the rail's width is a token too (`--rail`), paid for by `.app`'s `padding-left`; the top bar
  and the toast are `fixed`, so they repeat the same measure by hand.
- **Two builds are compared on the same ledger, with no focus lying around.** A comparison at 390
  and 768 is only worth the words if both sides saw the same data — a sync clicked between the two
  captures moved a balance and changed four elements, which looked exactly like a regression. And
  before a pixel comparison, blur the active element: the focus ring a previous interaction left on
  a button is a state of the session, not of the bundle, and cost one round of chasing it.
- **A sheet docks right above 1024, and that is all that changed about it.** `.sheet` is a `<dialog>`
  in the top layer, so `showModal()`, `Esc`, the backdrop and the focus trap are the browser's and
  stay untouched; the desktop block only moves the panel (`align-items: stretch`,
  `justify-content: flex-end`, a `clamp(460px, 40%, 520px)` width, full height, rounded on the left)
  and swaps its entrance for `sheet-in-right`, which is the bottom sheet's 30px travel rotated a
  quarter turn. The drag handle is hidden because it promises a downward close. The page behind is
  locked with `body:has(dialog[open]) { overflow: hidden }` — and that lock stops wheels and
  fingers, **not** `window.scrollTo` or a `scrollTop` assignment, so verify it with a real wheel
  event: scripted scrolling "proves" a lock that is not there. The lock also takes the page's
  scrollbar away, and with it the width the page lays out in: the centred column moved half of
  that and a panel flush with the right edge moved all of it. The same block reserves the gutter
  (`html { scrollbar-gutter: stable }`), so the locked and unlocked states share one width.
- **A grid's columns are not shared with the grid below it.** The movements table's header and its
  rows are two separate grids, so any `auto` column is sized from its own contents: with `auto`, the
  header's "Categoria" (58 px) sat over nothing while the rows' pills reached 293. The columns are
  fixed in `rem` for that reason, and the numbers come from the worst cell measured in a month. The
  same trap is why the row keeps one markup for both shapes: `display: contents` on
  `.txn__body`/`.txn__meta` hands their children to the row's grid above 1024, while below they are
  the phone's lines — and the eight screenshots at 390 and 768 stay byte-identical.
- **A control written once can be placed twice.** In the review queue the category select, its
  confirm button and the new-category form live in one function (`proposalControls`) and render both
  inside the card (below 1024, where the card is the detail) and inside the docked pane (above, where
  the pane is); the stylesheet hides whichever the width does not need, so there is one implementation
  and one set of controls on screen at a time.
