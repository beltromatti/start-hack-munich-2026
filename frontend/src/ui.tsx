import type { Bucket, Stage } from "./sim/sim";

const STAGE_LABEL: Record<Stage, string> = {
  received: "Received", pricing: "Pricing", waiting: "Waiting for carriers", quoted: "Quoted",
  accepted: "Accepted", booked: "Booked", lost: "Rejected", missed: "Missed",
};

export function StagePill({ stage }: { stage: Stage }) {
  return <span className={`pill s-${stage}`}>{STAGE_LABEL[stage]}</span>;
}

export function Dot({ bucket, title }: { bucket: Bucket; title?: string }) {
  return <span className={`dot b-${bucket}`} title={title ?? bucket} aria-label={bucket} />;
}

export function Kpi({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "good" | "warn" | "bad" }) {
  return (
    <div className="kpi">
      <span className="kpi-label">{label}</span>
      <span className={`kpi-value ${tone ?? ""}`}>{value}</span>
      {hint && <span className="kpi-hint">{hint}</span>}
    </div>
  );
}
