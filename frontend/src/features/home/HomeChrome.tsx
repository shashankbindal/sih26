import { Link } from 'react-router-dom';
import { ButtonLink } from '@/components/ui/Button';
import { Container } from './parts';
import { OPEN_WORDS_EVENT } from './WordsGuide';

export const PROTOTYPE_NOTE = 'Prototype · synthetic data modelled on the AICTE Permanent ID format';

export function TopBar() {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-surface">
      <Container className="flex h-[52px] items-center gap-5">
        <a href="#top" className="focus-ring flex items-baseline gap-2 rounded hover:no-underline">
          <span className="text-md font-semibold text-ink-900">Lok Sutra</span>
          <span lang="hi" className="text-sm text-ink-500">
            लोक सूत्र
          </span>
        </a>
        <a href="#flow" className="focus-ring ml-auto hidden rounded px-2 py-1.5 text-sm text-ink-700 hover:text-navy sm:block">
          How it works
        </a>
        <ButtonLink to="/login" variant="primary" className="ml-auto sm:ml-0">
          Sign in
        </ButtonLink>
      </Container>
    </header>
  );
}

export function HomeFooter() {
  return (
    <footer className="bg-ink-900 text-surface">
      <Container className="flex flex-col gap-3 py-6 text-sm sm:flex-row sm:items-center sm:justify-between">
        <p className="m-0">
          <span className="font-semibold">Lok Sutra {'·'} SIH 2026 {'·'} SIH26264 {'·'} Team Neurals Knight</span>
          <span className="mt-1 block text-xs text-on-dark">{PROTOTYPE_NOTE}</span>
        </p>
        <div className="flex items-center gap-4">
          <a
            href="#words"
            onClick={() => window.dispatchEvent(new Event(OPEN_WORDS_EVENT))}
            className="focus-ring rounded text-sm text-surface underline hover:text-on-dark"
          >
            Plain-word guide
          </a>
          <Link to="/login" className="focus-ring w-fit rounded border border-on-dark px-3 py-1.5 text-sm font-medium text-surface hover:bg-ink-700 hover:no-underline">
            Sign in
          </Link>
        </div>
      </Container>
    </footer>
  );
}
