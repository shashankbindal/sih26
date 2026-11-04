import { ButtonLink } from '@/components/ui/Button';
import { RelationBadge } from '@/components/domain/RelationBadge';
import { Container, Section, SectionHeader } from './parts';
import { PROBLEMS } from './content';

/** Title statement plus the small three-records card the presenter points at. */
export function Hero() {
  return (
    <section id="top" aria-labelledby="top-h" className="border-b border-line bg-surface">
      <Container className="grid gap-10 py-12 md:py-14 lg:grid-cols-2 lg:items-center">
        <div>
          <h1 id="top-h" className="text-[32px] font-semibold leading-[1.1] text-ink-900 sm:text-[42px]">
            <span className="block">One institution.</span> <span className="block">One truth.</span>
          </h1>
          <p lang="hi" className="mt-2 text-[16px] text-ink-500">
            एक संस्थान, एक सत्य
          </p>
          <p className="mt-5 max-w-[480px] text-[18px] leading-relaxed text-ink-700">
            Lok Sutra gives every AICTE officer one verified view of a college, and tells them when another team is already acting on it.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <ButtonLink to="/login" variant="primary" className="h-10 px-4 text-[15px]">
              Sign in to the prototype
            </ButtonLink>
            <a
              href="#flow"
              className="focus-ring inline-flex h-10 items-center justify-center rounded border border-line bg-surface px-4 text-[15px] font-medium text-ink-900 hover:bg-paper hover:no-underline"
            >
              See how it works
            </a>
          </div>
        </div>

        <figure className="m-0 min-w-0">
          <figcaption className="mb-2 text-sm font-semibold text-ink-900">One college, as the bureaus see it today</figcaption>
          <div role="region" aria-label="Example records for one college" tabIndex={0} className="focus-ring overflow-x-auto rounded border border-line bg-surface">
            <table className="ls-table compact">
              <thead>
                <tr>
                  <th scope="col">Door</th>
                  <th scope="col">Handled by</th>
                  <th scope="col">Name as written</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>AICTE complaint portal (CSS)</td>
                  <td>Complaint cell (PGRC)</td>
                  <td lang="hi">श्रीनाथ इंजीनियरिंग कॉलेज</td>
                </tr>
                <tr>
                  <td>Public grievance portal (CPGRAMS)</td>
                  <td>Complaint cell</td>
                  <td>Shrinath Engg. College</td>
                </tr>
                <tr>
                  <td>Regional office (RO) register</td>
                  <td>Kanpur regional office</td>
                  <td>Shrinath Inst. of Engineering, Kanpur</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div className="mt-3 border-l-4 border-saffron bg-saffron-bg px-3 py-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-ink-900">Lok Sutra view</span>
              <RelationBadge relation="RELATED" />
            </div>
            <p className="m-0 mt-1 text-sm text-ink-700">Three records, one college. The complaint cell and the Kanpur regional office are both acting, and each is told about the other.</p>
          </div>
          <p className="mt-2 text-xs text-ink-500">Synthetic example.</p>
        </figure>
      </Container>
    </section>
  );
}

export function Problem() {
  return (
    <Section id="problem">
      <SectionHeader id="problem" title="The problem" hi="समस्या" />
      <ul className="m-0 grid list-none gap-x-8 gap-y-6 p-0 md:grid-cols-3">
        {PROBLEMS.map((p) => (
          <li key={p.lead} className="border-t-2 border-navy pt-3">
            <h3 className="m-0 text-[17px] font-semibold leading-snug text-ink-900">{p.lead}</h3>
            <p className="m-0 mt-1.5 text-[16px] leading-relaxed text-ink-700">{p.line}</p>
          </li>
        ))}
      </ul>
    </Section>
  );
}
