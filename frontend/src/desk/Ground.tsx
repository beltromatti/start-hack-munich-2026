import { useEffect, useRef } from "react";

// The ground the desk sits on: two soft spheres of colour with grain, drawn live, drifting slowly.
// Their colour is the state of the desk at a glance: green while everything runs on its own, amber when
// there are notes to read, red when something is wrong. They swell once when the state changes and hold
// still for people who ask for less motion.
export type Mood = "calm" | "watch" | "alert";
// paper, then per sphere: highlight, core, depth
const PAL: Record<Mood, string[]> = {
  calm: ["#eef2e8", "#c9f0cf", "#3fae6c", "#1d7d4b", "#e3f3c6", "#8fcf8a", "#3f9a66"],
  watch: ["#f3efe2", "#fbe7b2", "#e7a83a", "#c27d14", "#f7edc4", "#e6c56a", "#c99a35"],
  alert: ["#f4e9e4", "#fbcdbd", "#e8573c", "#b9341f", "#f9d9c2", "#f08f6c", "#d0553a"],
};
const rgb = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));

export function Ground({ mood }: { mood: Mood }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const target = useRef(mood);
  const swell = useRef(0);
  useEffect(() => { if (target.current !== mood) swell.current = 1; target.current = mood; }, [mood]);
  useEffect(() => {
    const cv = ref.current, ctx = cv?.getContext("2d");
    if (!cv || !ctx) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let now = PAL[target.current].map(rgb), raf = 0, px = 0.5, py = 0.5, sx = 0.5, sy = 0.5;
    const move = (e: PointerEvent) => { px = e.clientX / window.innerWidth; py = e.clientY / window.innerHeight; };
    window.addEventListener("pointermove", move, { passive: true });
    const sphere = (x: number, y: number, r: number, i: number) => {
      const c = (k: number, a: number) => "rgba(" + now[k].map(Math.round).join(",") + "," + a + ")";
      const g = ctx.createRadialGradient(x - r * 0.32, y - r * 0.36, r * 0.04, x, y, r);
      g.addColorStop(0, c(i, 1)); g.addColorStop(0.42, c(i + 1, 0.96)); g.addColorStop(0.74, c(i + 2, 0.82)); g.addColorStop(1, c(i + 2, 0));
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    };
    const draw = (ms: number) => {
      const t = still ? 0 : ms / 1000, want = PAL[target.current].map(rgb), w = cv.width, h = cv.height;
      now = now.map((c, i) => c.map((v, k) => still ? want[i][k] : v + (want[i][k] - v) * 0.03));
      swell.current *= 0.982;
      const s = 1 + swell.current * 0.22 + (still ? 0 : Math.sin(t * 0.5) * 0.025);
      ctx.fillStyle = "rgb(" + now[0].map(Math.round).join(",") + ")"; ctx.fillRect(0, 0, w, h);
      sx += (px - sx) * 0.05; sy += (py - sy) * 0.05; // the colour leans toward the pointer, a moment behind it
      sphere(w * (0.13 + Math.sin(t * 0.07) * 0.04 + (sx - 0.5) * 0.12), h * (0.72 + Math.cos(t * 0.06) * 0.06 + (sy - 0.5) * 0.1), h * 0.62 * s, 1);
      sphere(w * (0.9 + Math.cos(t * 0.05) * 0.04 - (sx - 0.5) * 0.1), h * (0.16 + Math.sin(t * 0.08) * 0.05 - (sy - 0.5) * 0.08), h * 0.44 * s, 4);
      if (!still) raf = requestAnimationFrame(draw);
    };
    const tick = still ? window.setInterval(() => draw(0), 1200) : 0;
    raf = requestAnimationFrame(draw);
    return () => { cancelAnimationFrame(raf); if (tick) clearInterval(tick); window.removeEventListener("pointermove", move); };
  }, []);
  return <div className="dk-ground" aria-hidden="true"><canvas ref={ref} width={480} height={300} /></div>;
}

// The mark: an origin and a destination grown into one shape, and the shipment that has just left.
export function Mark({ size = 30 }: { size?: number }) {
  return (
    <svg className="dk-mark" width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <defs><filter id="dk-goo" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur in="SourceGraphic" stdDeviation="3.4" /><feColorMatrix values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 28 -12" /></filter></defs>
      <g filter="url(#dk-goo)" fill="currentColor" stroke="currentColor"><circle cx="21" cy="42" r="15" stroke="none" /><circle cx="42" cy="23" r="9.5" stroke="none" /><path d="M28 36 39 26" strokeWidth="6.5" strokeLinecap="round" /></g>
      <circle cx="56" cy="10" r="4.4" fill="currentColor" />
    </svg>
  );
}
