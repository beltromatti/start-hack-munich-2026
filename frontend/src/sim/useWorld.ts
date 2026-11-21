import { useEffect, useState } from "react";
import { SPEED, START_AT, world, type World } from "./sim";

/** Simulated clock: advances SPEED simulated seconds per real second unless paused. */
export function useWorld(): { w: World; paused: boolean; toggle: () => void } {
  const [now, setNow] = useState(START_AT);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => setNow((n) => n + SPEED / 4), 250);
    return () => clearInterval(t);
  }, [paused]);
  return { w: world(now), paused, toggle: () => setPaused((p) => !p) };
}
