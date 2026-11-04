export const API_BASE: string = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1').replace(/\/+$/, '');
export const DEMO_MODE: boolean = String(import.meta.env.VITE_DEMO_MODE ?? 'false').toLowerCase() === 'true';
