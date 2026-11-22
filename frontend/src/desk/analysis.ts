// The shape the matrix chart draws: how figures about the shipments move together (Pearson r). The numbers are
// computed in the backend from the register (backend/app/charts.py); the assistant chooses when to show them.
export type Matrix = { vars: string[]; r: (number | null)[][]; n: number; target: string; text: string; insights: string[]; example: boolean };

export const fmt = (r: number | null) => r == null ? "n/a" : (r >= 0 ? "+" : "") + r.toFixed(2);
