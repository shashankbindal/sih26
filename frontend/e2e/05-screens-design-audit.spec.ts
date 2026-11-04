import { test, expect, type Page } from '@playwright/test';
import AxeSource from 'axe-core';
import fs from 'node:fs';
import path from 'node:path';
import { api, institutionId, loginAs, settle, shot, SHOTS, type Who } from './helpers';

const EMOJI = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/u;
const ALLOWED_GLYPHS = new Set(['✓', '✗']);
const findings: Record<string, any> = { screens: {}, axe: {} };
const OUT = path.resolve(SHOTS, '..', 'qa-runtime-audit.json');

interface Screen { name: string; who: Who | null; url: string | (() => Promise<string>); tab?: string; wide?: [number, number]; ready?: RegExp | string }

/** Runtime design audit evaluated inside the page. */
async function audit(page: Page) {
  return page.evaluate(
    ({ emojiSrc }) => {
      const out: any = { gradients: [], backdrop: [], blur: [], bigRadius: [], bigShadow: [], saffron: [], emoji: [], idsNotMono: [], numsNotTabular: [], fonts: {}, hscroll: {}, inter: [], pie: 0 };
      const emojiRe = new RegExp(emojiSrc, 'u');
      const all = Array.from(document.querySelectorAll<HTMLElement>('body *'));
      const desc = (el: Element) => `${el.tagName.toLowerCase()}${el.className && typeof el.className === 'string' ? '.' + el.className.split(/\s+/).slice(0, 3).join('.') : ''} "${(el.textContent ?? '').trim().slice(0, 30)}"`;
      const famSeen: Record<string, number> = {};
      for (const el of all) {
        const cs = getComputedStyle(el);
        if (cs.backgroundImage.includes('gradient')) out.gradients.push(desc(el));
        if ((cs.backdropFilter && cs.backdropFilter !== 'none') || ((cs as any).webkitBackdropFilter && (cs as any).webkitBackdropFilter !== 'none')) out.backdrop.push(desc(el));
        if (cs.filter.includes('blur')) out.blur.push(desc(el));
        const r = parseFloat(cs.borderTopLeftRadius);
        if (r >= 8 && el.getBoundingClientRect().width > 40 && !(el instanceof SVGElement)) out.bigRadius.push(`${r}px ${desc(el)}`);
        const sh = cs.boxShadow;
        if (sh && sh !== 'none') {
          const m = sh.match(/(\d+)px\s+(\d+)px\s+(\d+)px/g);
          if (m && m.some((x) => parseInt(x.split(' ')[2]) > 16)) out.bigShadow.push(`${sh.slice(0, 50)} ${desc(el)}`);
        }
        for (const prop of ['color', 'backgroundColor', 'borderTopColor', 'borderLeftColor', 'fill', 'stroke'] as const) {
          const v = (cs as any)[prop] as string;
          if (v === 'rgb(217, 130, 43)' || v === 'rgb(253, 241, 228)') out.saffron.push(`${prop}=${v} ${desc(el)} ctx:${(el.closest('[data-testid],section,table,a,button') as HTMLElement | null)?.tagName ?? ''}`);
        }
        const own = Array.from(el.childNodes).filter((n) => n.nodeType === 3).map((n) => n.textContent ?? '').join('');
        if (own.trim()) {
          for (const ch of own) if (emojiRe.test(ch) && ch !== '✓' && ch !== '✗') { out.emoji.push(`${ch.codePointAt(0)!.toString(16)} in ${desc(el)}`); break; }
          if (/^\s*(LS-\d{4}-\d{6}|1-\d{7,11})\s*$/.test(own) && !cs.fontFamily.includes('IBM Plex Mono')) out.idsNotMono.push(`${own.trim()} -> ${cs.fontFamily.slice(0, 40)}`);
          if (/^\s*[\d,]+(\.\d+)?\s*$/.test(own) && el.closest('td')) {
            if (!cs.fontVariantNumeric.includes('tabular-nums') && !cs.fontFamily.includes('Mono')) out.numsNotTabular.push(`${own.trim()} ${desc(el)}`);
          }
          const fam = cs.fontFamily.split(',')[0].replace(/"/g, '').trim();
          famSeen[fam] = (famSeen[fam] ?? 0) + 1;
          if (/inter\b/i.test(cs.fontFamily.split(',')[0])) out.inter.push(desc(el));
        }
      }
      out.fonts.families = famSeen;
      out.fonts.loaded = Array.from((document as any).fonts).filter((f: any) => f.status === 'loaded').map((f: any) => `${f.family} ${f.weight}`);
      const de = document.documentElement;
      out.hscroll = { doc: de.scrollWidth - de.clientWidth, body: document.body.scrollWidth - document.body.clientWidth };
      const main = document.querySelector('main') as HTMLElement | null;
      if (main) out.hscroll.main = main.scrollWidth - main.clientWidth;
      const hi = document.querySelector('[lang="hi"]');
      out.hindiLang = !!hi;
      out.hindiOnPage = /[ऀ-ॿ]/.test(document.body.innerText);
      out.statusBadges = document.querySelectorAll('[class*="badge"], .badge, [class*="tag"]').length;
      out.tablesWithoutTh = Array.from(document.querySelectorAll('table')).filter((t) => !t.querySelector('th[scope]')).length;
      return out;
    },
    { emojiSrc: EMOJI.source },
  );
}

async function runAxe(page: Page) {
  await page.addScriptTag({ content: AxeSource.source });
  return page.evaluate(async () => {
    const r = await (window as any).axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } });
    return r.violations.map((v: any) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length, sample: v.nodes.slice(0, 3).map((n: any) => `${n.target.join(' ')} :: ${(n.any[0]?.message ?? n.all[0]?.message ?? n.none[0]?.message ?? '').slice(0, 140)}`) }));
  });
}

let ids: { shr: string; link: string; caseId: string; rbCase: string };

test.beforeAll(async () => {
  const shr = await institutionId('admin', '1-4463974255');
  const dev = await institutionId('admin', '1-4471203398');
  const links = await api('admin', 'GET', `/institutions/${dev}/links`);
  const tl = await api('admin', 'GET', `/institutions/${shr}/timeline`);
  const items = tl.items ?? tl;
  ids = { shr, link: links[0].id, caseId: items.find((c: any) => c.owner_bureau === 'PGRC').id, rbCase: items.find((c: any) => c.owner_bureau === 'RB').id };
});

test.afterAll(() => {
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(findings, null, 1));
});

const SCREENS: Screen[] = [
  { name: 'dashboard', who: 'pgrc.officer', url: '/', wide: [1920, 1080] },
  { name: 'cases', who: 'pgrc.officer', url: '/cases', wide: [820, 1180] },
  { name: 'case-summary', who: 'pgrc.officer', url: async () => `/cases/${ids.caseId}` },
  { name: 'case-passport', who: 'pgrc.officer', url: async () => `/cases/${ids.caseId}`, tab: 'Case Passport' },
  { name: 'case-linked', who: 'pgrc.officer', url: async () => `/cases/${ids.caseId}`, tab: 'Linked cases' },
  { name: 'case-sources', who: 'pgrc.officer', url: async () => `/cases/${ids.caseId}`, tab: 'Source records' },
  { name: 'new-case', who: 'pgrc.officer', url: '/cases/new' },
  { name: 'institutions', who: 'pgrc.officer', url: '/institutions' },
  { name: 'institution-360', who: 'pgrc.officer', url: async () => `/institutions/${ids.shr}`, wide: [1920, 1080] },
  { name: 'coordination', who: 'pgrc.head', url: '/coordination' },
  { name: 'link-compare', who: 'rb.head', url: async () => `/coordination/${ids.link}` },
  { name: 'clearances', who: 'pgrc.officer', url: '/clearances' },
  { name: 'review', who: 'pgrc.officer', url: '/review' },
  { name: 'import', who: 'pgrc.officer', url: '/import' },
  { name: 'reports', who: 'mgmt', url: '/reports' },
  { name: 'evaluation', who: 'pgrc.officer', url: '/evaluation' },
  { name: 'admin-thresholds', who: 'admin', url: '/admin' },
  { name: 'admin-demo-tools', who: 'admin', url: '/admin', tab: 'Demo tools' },
];

for (const s of SCREENS) {
  test(`screen ${s.name}: screenshot, runtime design audit${['dashboard', 'institution-360', 'cases'].includes(s.name) ? ', axe' : ''}`, async ({ page }) => {
    if (s.who) await loginAs(page, s.who);
    const url = typeof s.url === 'function' ? await s.url() : s.url;
    await page.goto(url);
    if (s.tab) await page.getByRole('tab', { name: new RegExp(s.tab) }).click();
    await settle(page);
    await page.waitForTimeout(600);
    await shot(page, s.name);
    const a = await audit(page);
    findings.screens[s.name] = a;
    expect.soft(a.gradients, 'gradient backgrounds').toEqual([]);
    expect.soft(a.backdrop, 'backdrop-filter').toEqual([]);
    expect.soft(a.blur, 'filter blur').toEqual([]);
    expect.soft(a.emoji, 'emoji').toEqual([]);
    expect.soft(a.idsNotMono, 'IDs not in mono').toEqual([]);
    expect.soft(a.inter, 'Inter font').toEqual([]);
    expect.soft(a.hscroll.doc, 'document horizontal overflow @1366').toBeLessThanOrEqual(0);
    expect.soft(a.hscroll.main ?? 0, 'main horizontal overflow @1366').toBeLessThanOrEqual(0);
    if (['dashboard', 'institution-360', 'cases'].includes(s.name)) {
      const v = await runAxe(page);
      findings.axe[s.name] = v;
    }
    if (s.wide) {
      await page.setViewportSize({ width: s.wide[0], height: s.wide[1] });
      await settle(page);
      await page.waitForTimeout(500);
      await shot(page, `${s.name}-${s.wide[0]}x${s.wide[1]}`);
      const w = await audit(page);
      findings.screens[`${s.name}@${s.wide[0]}`] = { hscroll: w.hscroll };
      if (s.wide[0] < 1000) expect.soft(w.hscroll.doc, 'tablet horizontal overflow').toBeLessThanOrEqual(0);
    }
  });
}

test('login screen audit', async ({ page }) => {
  await page.goto('/login');
  await settle(page);
  const a = await audit(page);
  findings.screens['login'] = a;
  expect.soft(a.gradients).toEqual([]);
  expect.soft(a.emoji).toEqual([]);
  expect(a.hindiOnPage).toBeTruthy();
});

test('Devanagari renders in Noto Sans Devanagari and fonts are Plex', async ({ page }) => {
  await loginAs(page, 'pgrc.officer');
  await page.goto('/cases/new');
  await page.getByRole('button', { name: 'Demo inputs' }).click();
  await page.getByRole('menuitem', { name: /Scenario A/ }).click();
  await settle(page);
  const r = await page.evaluate(async () => {
    await (document as any).fonts.ready;
    const faces = Array.from((document as any).fonts).filter((f: any) => f.status === 'loaded').map((f: any) => f.family.replace(/"/g, ''));
    const body = getComputedStyle(document.body).fontFamily;
    return { faces: Array.from(new Set(faces)), body, plexSans: (document as any).fonts.check('13px "IBM Plex Sans"'), plexMono: (document as any).fonts.check('13px "IBM Plex Mono"'), noto: (document as any).fonts.check('13px "Noto Sans Devanagari"', 'श्री') };
  });
  findings.fonts = r;
  expect(r.faces.join()).toContain('IBM Plex Sans');
  expect(r.faces.join()).toContain('Noto Sans Devanagari');
  expect(r.body).toContain('IBM Plex Sans');
});
