import { useEffect, useState } from 'react';
import { Container } from './parts';
import { WORDS } from './content';

export const OPEN_WORDS_EVENT = 'ls:open-words';

/** Collapsed glossary near the footer. Opens from the footer link, from #words in the URL, or by clicking the summary. */
export function WordsGuide() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const openIt = () => setOpen(true);
    const onHash = () => window.location.hash === '#words' && openIt();
    onHash();
    window.addEventListener('hashchange', onHash);
    window.addEventListener(OPEN_WORDS_EVENT, openIt);
    return () => {
      window.removeEventListener('hashchange', onHash);
      window.removeEventListener(OPEN_WORDS_EVENT, openIt);
    };
  }, []);
  return (
    <section id="words" aria-label="Words used on this page" className="scroll-mt-14 border-b border-line bg-paper py-8">
      <Container>
      <details open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary className="focus-ring inline-block cursor-pointer rounded py-1 text-[16px] font-semibold text-ink-900">Words used on this page</summary>
        <div className="mt-3 overflow-hidden rounded border border-line bg-surface">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-paper text-left text-ink-700">
                <th scope="col" className="w-[42%] border-b border-line px-3 py-2 font-semibold">Technical term</th>
                <th scope="col" className="border-b border-line px-3 py-2 font-semibold">In plain words</th>
              </tr>
            </thead>
            <tbody>
              {WORDS.map(([term, plain]) => (
                <tr key={term}>
                  <th scope="row" className="border-b border-line-soft px-3 py-2 text-left align-top font-medium text-ink-900">{term}</th>
                  <td className="border-b border-line-soft px-3 py-2 align-top text-ink-700">{plain}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      </Container>
    </section>
  );
}
