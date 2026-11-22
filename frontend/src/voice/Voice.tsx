import { useEffect, useMemo, useRef, useState } from "react";
import type { DealRow } from "../api";
import { post } from "../api";
import { Answer, answer, askModel } from "../desk/ask";
import { Ground, Mood } from "../desk/Ground";
import { context, useKnowledge } from "../desk/knowledge";
import { city, ends, name } from "../desk/util";
import "../desk/desk.css";
import "./voice.css";

// The voice desk: a person talks to the desk on a phone and hears its answer. The same record as Sam's desk
// (/api/deals, the customers and carriers in context()), the same assistant (/api/ask), and the same way to
// reach Giulia (her session's message endpoint). Nothing here decides: a tell goes out only after a yes.
// The orb rests on the horizon and rises to the centre while a conversation runs.
type Step = "idle" | "listening" | "thinking" | "speaking" | "confirm" | "done";
const YES = /^(yes|yeah|yep|sure|ok(ay)?|do it|go( ahead)?|send( it)?|tell (her|giulia)|please|ja|jo|klar|mach|sì|si|va bene)\b/i;
const NO = /^(no|nope|not now|cancel|stop|nein|lass|nicht)\b/i;
type Rec = { stop: () => void };
type SpeechRec = { lang: string; interimResults: boolean; continuous: boolean; start: () => void; stop: () => void;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; onend: (() => void) | null; onerror: (() => void) | null };
const W = window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec };
const SR = W.SpeechRecognition ?? W.webkitSpeechRecognition;

export function Voice({ deals }: { deals: DealRow[] }) {
  const [step, setStep] = useState<Step>("idle");
  const [heard, setHeard] = useState("");
  const [ans, setAns] = useState<Answer | null>(null);
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState("");
  const [eleven, setEleven] = useState(false);
  const { seen } = useKnowledge(deals);
  const orb = useRef<HTMLSpanElement>(null);
  const level = useRef(0);            // 0..1, what the orb breathes with
  const source = useRef<"none" | "fake" | "node">("none");
  const analyser = useRef<AnalyserNode | null>(null);
  const audio = useRef<AudioContext | null>(null);
  const rec = useRef<Rec | null>(null);
  const earlier = useRef<{ q: string; a: string }[]>([]);
  const ansRef = useRef<Answer | null>(null); ansRef.current = ans;

  // an app on the home screen: name, icon, full screen, no browser bar
  useEffect(() => {
    document.title = "Desk";
    const add = (tag: string, attrs: Record<string, string>) => { const el = document.createElement(tag); Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v)); document.head.appendChild(el); return el; };
    const els = [add("link", { rel: "manifest", href: "/voice.webmanifest" }), add("link", { rel: "apple-touch-icon", href: "/voice-180.png" }),
      add("meta", { name: "apple-mobile-web-app-capable", content: "yes" }), add("meta", { name: "mobile-web-app-capable", content: "yes" }),
      add("meta", { name: "apple-mobile-web-app-status-bar-style", content: "default" }), add("meta", { name: "apple-mobile-web-app-title", content: "Desk" }),
      add("meta", { name: "theme-color", content: "#eef2e8" })];
    const vp = document.querySelector("meta[name=viewport]"), was = vp?.getAttribute("content") ?? "";
    vp?.setAttribute("content", "width=device-width, initial-scale=1, viewport-fit=cover");
    fetch("/api/voice").then((r) => r.json()).then((j: { voice: boolean }) => setEleven(!!j.voice)).catch(() => setEleven(false));
    return () => { els.forEach((e) => e.remove()); vp?.setAttribute("content", was); };
  }, []);

  // the orb's breath: the real signal when there is one, a speech-like wave when the browser speaks
  useEffect(() => {
    let raf = 0; const buf = new Uint8Array(256);
    const tick = (ms: number) => {
      let want = 0;
      if (source.current === "node" && analyser.current) {
        analyser.current.getByteTimeDomainData(buf);
        let sum = 0; for (const v of buf) sum += (v - 128) * (v - 128);
        want = Math.min(1, Math.sqrt(sum / buf.length) / 28);
      } else if (source.current === "fake") {
        const t = ms / 1000; want = Math.max(0, Math.sin(t * 9.3) * 0.5 + Math.sin(t * 4.1 + 1) * 0.35 + Math.sin(t * 17) * 0.15);
      }
      level.current += (want - level.current) * 0.35;
      orb.current?.style.setProperty("--lvl", level.current.toFixed(3));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  const ctx = () => { if (!audio.current) audio.current = new AudioContext(); void audio.current.resume(); return audio.current; };
  const listenTo = (node: AudioNode) => { const a = ctx().createAnalyser(); a.fftSize = 256; node.connect(a); analyser.current = a; source.current = "node"; return a; };
  const stopAll = () => { rec.current?.stop(); rec.current = null; if ("speechSynthesis" in window) speechSynthesis.cancel(); source.current = "none"; };

  // speaking: ElevenLabs through our backend, else the browser's voice
  const speak = async (text: string) => {
    setStep("speaking");
    if (eleven) {
      try {
        const r = await fetch("/api/voice/speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
        if (!r.ok) throw new Error(String(r.status));
        const el = new Audio(URL.createObjectURL(await r.blob()));
        listenTo(ctx().createMediaElementSource(el)).connect(ctx().destination);
        await new Promise<void>((done) => { el.onended = () => done(); el.onerror = () => done(); void el.play().catch(() => done()); });
        source.current = "none"; return;
      } catch { /* the browser speaks instead */ }
    }
    if (!("speechSynthesis" in window)) return;
    await new Promise<void>((done) => {
      const u = new SpeechSynthesisUtterance(text); u.lang = "en-GB"; u.rate = 1.04;
      u.onstart = () => { source.current = "fake"; }; u.onend = () => done(); u.onerror = () => done();
      speechSynthesis.cancel(); speechSynthesis.speak(u);
      window.setTimeout(done, 1500 + text.length * 90); // a voice that never ends must not hold the page
    });
    source.current = "none";
  };

  // hearing: ElevenLabs Scribe on a recording that ends by itself after a pause, else the browser's recognition
  const listen = async () => {
    stopAll(); setHeard(""); setNote(""); setTyping(false); setStep("listening");
    const back = () => setStep(ansRef.current?.act ? "confirm" : "idle");
    if (eleven && navigator.mediaDevices?.getUserMedia && "MediaRecorder" in window) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        listenTo(ctx().createMediaStreamSource(stream));
        const mr = new MediaRecorder(stream), parts: Blob[] = [];
        let spoke = 0, quiet = 0, finished = false;
        const watch = window.setInterval(() => {
          if (level.current > 0.12) { spoke += 1; quiet = 0; } else if (spoke > 3) quiet += 1;
          if (quiet > 14 || spoke + quiet > 300) mr.stop(); // 1.4 s of quiet after speech, or 30 s in all
        }, 100);
        mr.ondataavailable = (e) => parts.push(e.data);
        mr.onstop = async () => {
          if (finished) return; finished = true;
          clearInterval(watch); stream.getTracks().forEach((t) => t.stop()); source.current = "none"; rec.current = null;
          const blob = new Blob(parts, { type: mr.mimeType || "audio/webm" });
          if (!spoke || !blob.size) { back(); return; }
          setStep("thinking");
          const r = await fetch("/api/voice/hear", { method: "POST", headers: { "Content-Type": blob.type }, body: blob }).then((x) => x.ok ? x.json() : null).catch(() => null) as { text: string } | null;
          if (r?.text) heardAll(r.text); else { setNote("I did not catch that. Tap and say it again."); back(); }
        };
        mr.start(); rec.current = { stop: () => { if (mr.state !== "inactive") mr.stop(); } }; return;
      } catch { setNote("The microphone is blocked. Allow it in the browser, or type."); back(); return; }
    }
    if (!SR) { setNote("This browser cannot listen. Type instead."); setTyping(true); back(); return; }
    const r = new SR(); r.lang = navigator.language || "en-GB"; r.interimResults = true; r.continuous = false;
    let last = "";
    r.onresult = (e) => { last = Array.from(e.results).map((x) => x[0].transcript).join(" "); setHeard(last); };
    r.onend = () => { rec.current = null; source.current = "none"; if (last.trim()) heardAll(last); else back(); };
    r.onerror = () => setNote("I did not catch that. Tap and say it again.");
    source.current = "fake"; r.start(); rec.current = { stop: () => r.stop() };
  };

  // what was said: a yes or no to the open tell, or a new question
  const heardAll = (text: string) => {
    const q = text.trim(); setHeard(q);
    const open = ansRef.current?.act;
    if (open && YES.test(q)) { void tell(); return; }
    if (open && NO.test(q)) { setAns(null); void speak("Fine. Nothing goes to Giulia.").then(() => setStep("idle")); return; }
    void ask(q);
  };
  const ask = async (q: string) => {
    setStep("thinking"); setAns(null);
    const a = await askModel(q, deals, context(deals, seen), earlier.current.slice(-3)).catch(() => ({ ...answer(q, deals), via: "record" as const }));
    earlier.current.push({ q, a: a.text }); setAns(a); ansRef.current = a;
    await speak(a.text);
    if (a.act) { setStep("confirm"); void listen(); } else setStep("idle");
  };
  const tell = async () => {
    const a = ansRef.current?.act; if (!a) return;
    stopAll(); setStep("thinking");
    try {
      await post("/api/sessions/" + a.deal.replace(/^deal-/, "session-") + "/message", { text: a.text, who: "Voice desk" });
      setStep("done"); await speak("Passed on. Giulia acts on it now."); setStep("done");
    } catch { setNote("That did not reach Giulia. Try again."); setStep("confirm"); }
  };
  const cancel = () => { stopAll(); setAns(null); setHeard(""); setNote(""); setStep("idle"); };

  const act = ans?.act;
  const deal = act ? deals.find((d) => d.id === act.deal) ?? ans?.rows?.[0] : undefined;
  const route = deal ? ends(deal) : null;
  const live = step === "listening" || step === "thinking" || step === "speaking" || step === "confirm";
  const mood: Mood = (step === "speaking" && act) || step === "confirm" ? "watch" : "calm";
  const label = { idle: "Desk", listening: "Listening", thinking: "Looking it up", speaking: "Desk", confirm: "Waiting for your yes", done: "Handed to Giulia" }[step];
  const words = useMemo(() => {
    if (step === "listening") return <p>{heard || "Go ahead"}<em> …</em></p>;
    if (step === "thinking") return <>{heard ? <p className="vo-you">{heard}</p> : null}<span className="vo-think"><i /><i /><i /></span></>;
    if (step === "done") return <><p className="vo-fx">Giulia has it.</p><p className="vo-sub">{deal ? "Her next mail to " + name(deal) + " shows in the shipment." : "Her next step shows in the shipment."}</p></>;
    if (step === "confirm" && act) return <p>Tell Giulia: “{act.text}”?</p>;
    if (ans) return <>{heard ? <p className="vo-you">{heard}</p> : null}<p className="vo-fx vo-ans">{ans.text}</p></>;
    return <p>What changed?<br /><em>Say it like you would to a colleague.</em></p>;
  }, [step, heard, ans, act, deal]);

  const talkOrStop = () => {
    if (step === "listening") rec.current?.stop();
    else if (step === "speaking") { stopAll(); setStep(act ? "confirm" : "idle"); }
    else void listen();
  };
  return (
    <div className="dk-app vo" data-mood={mood} data-step={step}>
      <Ground mood={mood} />
      <div className={"vo-scr" + (live ? " live" : "")}>
        <div className="vo-top"><span className="vo-who"><b>Desk</b><small>{eleven ? "Voice on" : "Browser voice"}</small></span></div>
        <div className="vo-carrier"><span className="vo-orb" ref={orb} /></div>
        <div className="vo-words" aria-live="polite"><div className="vo-st"><i /><span className="vo-lbl">{label}</span></div>{words}{note ? <p className="vo-note">{note}</p> : null}</div>
        {step === "confirm" && act ? (
          <div className="vo-tell vo-fx">
            <div className="vo-h"><i>G</i>Giulia will act on this{deal ? " for " + name(deal) : ""}</div>
            <div className="vo-kv">
              {route ? <div><span>Route</span><b>{city(route[0])} to {city(route[1])}</b></div> : null}
              {(ans?.facts ?? []).slice(0, 3).map(([k, v]) => <div key={k}><span>{k}</span><b>{v}</b></div>)}
            </div>
          </div>
        ) : null}
        <div className="vo-dock">
          {typing ? (
            <form className="vo-type" onSubmit={(e) => { e.preventDefault(); const q = draft.trim(); if (!q) return; setDraft(""); setTyping(false); heardAll(q); }}>
              <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Type to the desk" aria-label="Type to the desk" />
              <button className="vo-mic s" type="submit" aria-label="Send"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg></button>
            </form>
          ) : step === "confirm" ? (
            <><button className="vo-btn" onClick={cancel}>Not now</button><button className="vo-btn k" onClick={() => void tell()}>Yes, tell her</button></>
          ) : (
            <>
              <button className="vo-ic" aria-label="Clear" onClick={cancel}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M6 6l12 12M18 6 6 18" /></svg></button>
              <button className="vo-mic" aria-label={step === "listening" || step === "speaking" ? "Stop" : "Talk"} onClick={talkOrStop}>
                {step === "listening" || step === "speaking" ? <svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="7" width="10" height="10" rx="2" /></svg>
                  : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>}
              </button>
              <button className="vo-ic" aria-label="Type" onClick={() => { stopAll(); setTyping(true); }}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><rect x="3" y="6" width="18" height="12" rx="2.5" /><path d="M7 10h.01M11 10h.01M15 10h.01M7 14h10" /></svg></button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
