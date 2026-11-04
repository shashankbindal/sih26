import { useMemo } from 'react';
import { CircleMarker, MapContainer, TileLayer, Tooltip as MapTooltip } from 'react-leaflet';
import { Link, useNavigate } from 'react-router-dom';
import 'leaflet/dist/leaflet.css';
import './region.css';
import { DataTable, type Column } from '@/components/ui';
import { formatNumber } from '@/lib/format';
import type { RegionRow } from './api';

export type LocatedRegion = RegionRow & { lat: number; lng: number };
import { casesLink, type DashFilters } from './filters';
import { OPEN_STATUSES } from '@/lib/constants';

// Three discrete steps on the status tokens (no gradient scale). Presentation only, not policy.
const STEP_LOW = 0.1;
const STEP_HIGH = 0.25;

// Leaflet paths need literal colours, so the tokens are resolved at render time.
function tok(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function colours() {
  return { low: tok('--ok', '#1e6b3a'), mid: tok('--amber', '#9a5b00'), high: tok('--red', '#a4262c') };
}

function step(share: number, c: ReturnType<typeof colours>): { fill: string; label: string } {
  if (share >= STEP_HIGH) return { fill: c.high, label: 'over 25% overdue' };
  if (share >= STEP_LOW) return { fill: c.mid, label: '10 to 25% overdue' };
  return { fill: c.low, label: 'under 10% overdue' };
}

export function RegionPanelBody({ rows, filters, height }: { rows: LocatedRegion[]; filters: DashFilters; height: number }) {
  const navigate = useNavigate();
  const c = colours();
  const legend = [
    { fill: c.low, label: 'Under 10%' },
    { fill: c.mid, label: '10 to 25%' },
    { fill: c.high, label: 'Over 25%' },
  ];
  const maxOpen = Math.max(1, ...rows.map((r) => r.open));
  const sorted = useMemo(() => [...rows].sort((a, b) => b.open - a.open), [rows]);
  const link = (ro: string) => casesLink(filters, { ro_code: ro, status: OPEN_STATUSES });

  const columns: Column<RegionRow>[] = [
    {
      key: 'name',
      header: 'Region',
      width: '55%',
      render: (r) => (
        <Link to={link(r.ro_code)} className="text-ink-900" title={r.name}>
          {r.city ?? r.name}
        </Link>
      ),
    },
    { key: 'open', header: 'Open', width: 50, numeric: true, render: (r) => formatNumber(r.open) },
    {
      key: 'overdue',
      header: 'Late',
      width: 50,
      numeric: true,
      render: (r) => <span className={r.overdue > 0 ? 'font-medium text-red' : ''}>{formatNumber(r.overdue)}</span>,
    },
  ];

  return (
    <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-3">
      <div>
        <div className="overflow-hidden rounded border border-line" style={{ height }}>
          <MapContainer center={[22.6, 79.4]} zoom={4} minZoom={3} scrollWheelZoom={false} style={{ height: '100%', width: '100%', background: '#eef1f4' }} attributionControl>
            <TileLayer
              url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
              attribution='Tiles &copy; <a href="https://www.esri.com">Esri</a>, HERE, Garmin, &copy; OpenStreetMap contributors'
              className="ls-map-tiles"
              maxZoom={16}
            />
            {rows.map((r) => {
              const share = r.open > 0 ? r.overdue / r.open : 0;
              const s = step(share, c);
              return (
                <CircleMarker
                  key={r.ro_code}
                  center={[r.lat, r.lng]}
                  radius={6 + 20 * Math.sqrt(r.open / maxOpen)}
                  pathOptions={{ color: s.fill, weight: 1.5, fillColor: s.fill, fillOpacity: 0.5 }}
                  eventHandlers={{ click: () => navigate(link(r.ro_code)) }}
                >
                  <MapTooltip direction="top">
                    <b>{r.name}</b> ({r.ro_code})
                    <br />
                    Open: {formatNumber(r.open)} · Overdue: {formatNumber(r.overdue)}
                    <br />
                    {s.label}
                  </MapTooltip>
                </CircleMarker>
              );
            })}
          </MapContainer>
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-500">
          <span className="w-full">Bubble size: open cases. Colour: share past a deadline.</span>
          {legend.map((l) => (
            <span key={l.label} className="inline-flex items-center gap-1">
              <span aria-hidden className="inline-block h-2.5 w-2.5" style={{ background: l.fill, opacity: 0.7, borderRadius: '50%' }} />
              {l.label}
            </span>
          ))}
        </div>
      </div>
      <DataTable compact caption="Open and overdue cases by Regional Office" columns={columns} rows={sorted} rowKey={(r) => r.ro_code} maxHeight={height} />
    </div>
  );
}
