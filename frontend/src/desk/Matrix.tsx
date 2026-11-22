import { useState } from "react";
import { Matrix, fmt } from "./analysis";

// A correlation matrix as a triangle of cells. Two hues with a neutral middle: cool where two things move
// together, warm where they move apart, grey where there is no link. Every cell carries its number, so nothing
// rests on colour alone, and a sentence under the chart says what the cell under the pointer means.
const MID = [240, 240, 238], APART = [181, 84, 31], TOGETHER = [31, 111, 139];
const mix = (to: number[], t: number) => "rgb(" + MID.map((v, k) => Math.round(v + (to[k] - v) * t)).join(",") + ")";
const css = (c: number[]) => "rgb(" + c.join(",") + ")";

export function MatrixChart({ m }: { m: Matrix }) {
  const [on, setOn] = useState<[number, number] | null>(null);
  const n = m.vars.length;
  if (m.n < 5) return null;
  const says = (i: number, j: number) => { const r = m.r[i][j]; return m.vars[i] + " and " + m.vars[j].toLowerCase() + ": " + fmt(r) + ". " + (r == null ? "Too few shipments have both." : Math.abs(r) < 0.15 ? "No clear link." : r > 0 ? "They tend to rise together." : "When one rises, the other tends to fall."); };
  return (
    <div className="dk-mx">
      <div className="dk-mx-grid" style={{ gridTemplateColumns: "minmax(110px, 170px) repeat(" + (n - 1) + ", minmax(0, 1fr))" }} role="table" aria-label={"How " + n + " variables move together across " + m.n + " quoted shipments"}>
        {m.vars.slice(1).map((row, a) => { const i = a + 1; return [
          <span key={row} className="rl" role="rowheader">{row}</span>,
          ...m.vars.slice(0, n - 1).map((colName, j) => { const r = m.r[i][j]; return j < i ? (
            <button key={row + colName} className="c" style={{ background: r == null ? "#f6f6f5" : mix(r < 0 ? APART : TOGETHER, Math.min(1, Math.abs(r)) ** 0.8), color: r != null && Math.abs(r) > 0.5 ? "#fff" : "#141414" }}
              aria-label={says(i, j)} onMouseEnter={() => setOn([i, j])} onMouseLeave={() => setOn(null)} onFocus={() => setOn([i, j])} onBlur={() => setOn(null)}>{r == null ? "n/a" : fmt(r)}</button>
          ) : <span key={row + colName} />; }),
        ]; })}
        <span />
        {m.vars.slice(0, n - 1).map((v) => <span key={v} className="cl">{v}</span>)}
      </div>
      <p className="dk-tip" aria-hidden="true">{on ? says(on[0], on[1]) : "Point at a cell to read it in words."}</p>
      <div className="dk-mx-leg"><span>Move apart</span><i style={{ background: "linear-gradient(90deg, " + css(APART) + ", " + css(MID) + ", " + css(TOGETHER) + ")" }} /><span>Move together</span><span className="n">{m.n} quoted shipments</span></div>
      {m.insights.length ? <ul className="dk-ins">{m.insights.map((s) => <li key={s}>{s}</li>)}</ul> : null}
      <p className="dk-fine" style={{ textAlign: "left", marginTop: 10 }}>{m.example ? "Margins are example values. Everything else is counted from the shipments. " : ""}A link is a hint where to look, not proof of a cause.</p>
    </div>
  );
}
