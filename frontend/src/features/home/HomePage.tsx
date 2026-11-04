import { useEffect } from 'react';
import { startWarmUp } from '@/api/client';
import { HomeFooter, TopBar } from './HomeChrome';
import { Hero, Problem } from './Intro';
import { Flow } from './Flow';
import { Architecture } from './Architecture';
import { MatrixSection } from './Matrix';
import { WordsGuide } from './WordsGuide';

/**
 * Public Home page (owner decision of 2026-11-02: one explanatory page outside the app shell).
 * Fully static: no API data, so it renders while the backend is still waking up.
 */
export default function HomePage() {
  useEffect(() => {
    document.title = 'Lok Sutra · One institution, one truth';
    // Wake the Render backend while the visitor reads. Already started once by App; this is a no-op then.
    startWarmUp();
  }, []);
  return (
    <div className="min-h-full bg-paper text-ink-900">
      <a
        href="#main"
        className="sr-only z-30 rounded border border-navy bg-surface px-3 py-2 text-sm font-medium text-navy focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
      >
        Skip to main content
      </a>
      <TopBar />
      <main id="main">
        <Hero />
        <Problem />
        <Flow />
        <Architecture />
        <MatrixSection />
        <WordsGuide />
      </main>
      <HomeFooter />
    </div>
  );
}
