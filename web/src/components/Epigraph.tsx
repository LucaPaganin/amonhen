import mark from "../assets/eye-mark.svg?raw";

/**
 * L'iscrizione in cima: la voce del luogo da cui l'app prende il nome.
 *
 * Il segno è l'Occhio sopra la torre, disegnato con i gettoni del tema — il
 * globo in ottone con la pupilla a fessura, le lingue di fuoco, la torre in un
 * riempimento basso — invece di un'icona presa da fuori: è la stessa grafite e
 * lo stesso ottone del resto, e si adatta da sé a una tavolozza che cambia. Il
 * disegno sta in `assets/eye-mark.svg`, che è anche la sorgente delle icone.
 */
export function Epigraph() {
  return (
    <figure className="epigraph">
      <span
        className="epigraph__mark"
        role="img"
        aria-label="L'Occhio sopra Barad-dûr"
        dangerouslySetInnerHTML={{ __html: mark }}
      />
      <figcaption className="epigraph__words">
        <p className="epigraph__quote">
          “There was an eye in the Dark Tower that did not sleep.”
        </p>
        <p className="epigraph__source">
          J.R.R. Tolkien, <i>The Fellowship of the Ring</i>
        </p>
      </figcaption>
    </figure>
  );
}
