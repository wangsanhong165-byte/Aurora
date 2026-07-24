const webSdkCheck = await agent({
  prompt: `Check what Live2D WebSDK files exist at C:/Users/LENOVO/Desktop/c++/ai/frontend/src/src/WebSDK/.
  1. List all files recursively
  2. Check if there's a bundled .js or .mjs file
  3. Look for any index.js, live2dcubismcore.min.js, or similar entry point
  4. Check if the old main.tsx or index.html references the SDK via script tag or import
  Report what the new frontend needs to reference to use Cubism 5 SDK.`,
  subagent_type: "general-purpose",
});

const deleteOld = await agent({
  prompt: `Delete the old frontend source code directories at C:/Users/LENOVO/Desktop/c++/ai/frontend/src/ but KEEP:
  - src/src/WebSDK/ (Live2D Cubism SDK - third party, must keep)
  - src/dist/ (build output)
  - src/package.json, tsconfig files, vite.config

  Delete these directories recursively using rm -rf:
  - src/src/main/
  - src/src/preload/
  - src/src/renderer/src/
  - src/src/renderer/public/

  After deletion, verify with: ls -la src/src/`,
  subagent_type: "general-purpose",
});

const scaffold = await agent({
  prompt: `Create a new Vite + React + TypeScript frontend project at C:/Users/LENOVO/Desktop/c++/ai/frontend/.

  First check tools: which node && node --version && which npm && npm --version

  Write these files:

  1. frontend/package.json:
  {"name":"companion-frontend","version":"1.0.0","private":true,"type":"module","scripts":{"dev":"vite","build":"tsc --noEmit && vite build","preview":"vite preview"},"dependencies":{"react":"^19.0.0","react-dom":"^19.0.0"},"devDependencies":{"@types/react":"^19.0.0","@types/react-dom":"^19.0.0","@vitejs/plugin-react":"^4.3.0","typescript":"^5.5.0","vite":"^6.0.0"}}

  2. frontend/vite.config.ts:
  import { defineConfig } from "vite";
  import react from "@vitejs/plugin-react";
  export default defineConfig({ plugins: [react()], build: { outDir: "dist" }, base: "/" });

  3. frontend/tsconfig.json:
  {"compilerOptions":{"target":"ES2020","module":"ESNext","moduleResolution":"bundler","jsx":"react-jsx","strict":true,"noEmit":true,"esModuleInterop":true,"forceConsistentCasingInFileNames":true,"resolveJsonModule":true,"isolatedModules":true,"skipLibCheck":true},"include":["src"]}

  4. frontend/index.html:
  <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/><title>Companion</title></head><body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body></html>

  5. Create directory structure: mkdir -p src/runtime src/audio src/character src/conversation src/styles src/components

  6. Run: cd /c/Users/LENOVO/Desktop/c++/ai/frontend && npm install 2>&1 | tail -20`,
  subagent_type: "general-purpose",
});

const runtimeLayer = await agent({
  prompt: `Create the runtime communication layer files at C:/Users/LENOVO/Desktop/c++/ai/frontend/src/.

  File 1: src/runtime/events.ts
  See the exact content below. Write it using the Write tool.

  export type ClientMessage =
    | { type: "user_message"; text: string }
    | { type: "audio_input"; data: string; format: string; sample_rate: number }
    | { type: "audio_end" }
    | { type: "interrupt" }
    | { type: "command"; action: string; payload?: Record<string, unknown> };

  export interface Segment { text: string; tone?: string; gesture?: string; }

  export type RuntimeStatus = "idle" | "listening" | "thinking" | "speaking";

  export type ServerMessage =
    | { type: "assistant_message"; text: string; segments?: Segment[] }
    | { type: "assistant_chunk"; text: string; index: number; final: boolean }
    | { type: "character_action"; action: string; intensity?: number; gesture?: string }
    | { type: "tts_audio"; data: string; format: string; volumes?: number[] }
    | { type: "runtime_status"; status: RuntimeStatus }
    | { type: "error"; code: string; message: string };

  File 2: src/runtime/state.ts
  import type { RuntimeStatus, Segment } from "./events";

  export interface RuntimeState {
    status: RuntimeStatus;
    currentText: string;
    segments: Segment[];
    characterAction: { action: string; intensity: number } | null;
    error: string | null;
    connected: boolean;
  }

  type Listener = (state: RuntimeState) => void;

  class RuntimeStore {
    private state: RuntimeState = {
      status: "idle", currentText: "", segments: [],
      characterAction: null, error: null, connected: false,
    };
    private listeners: Set<Listener> = new Set();
    getState(): RuntimeState { return this.state; }
    update(partial: Partial<RuntimeState>): void {
      this.state = { ...this.state, ...partial };
      this.listeners.forEach((l) => l(this.state));
    }
    subscribe(listener: Listener): () => void {
      this.listeners.add(listener);
      return () => this.listeners.delete(listener);
    }
  }
  export const runtimeStore = new RuntimeStore();

  File 3: src/runtime/client.ts
  import type { ClientMessage, ServerMessage } from "./events";
  import { runtimeStore } from "./state";

  const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000, 30000];

  export class RuntimeClient {
    private ws: WebSocket | null = null;
    private url: string;
    private reconnectAttempt = 0;
    private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    private intentionalClose = false;

    constructor(url?: string) { this.url = url || "ws://127.0.0.1:9528/client-ws"; }

    connect(): void {
      this.intentionalClose = false;
      if (this.ws?.readyState === WebSocket.OPEN) return;
      try { this.ws = new WebSocket(this.url); } catch { this.scheduleReconnect(); return; }
      this.ws.onopen = () => { this.reconnectAttempt = 0; runtimeStore.update({ connected: true, error: null }); };
      this.ws.onclose = () => { runtimeStore.update({ connected: false }); if (!this.intentionalClose) this.scheduleReconnect(); };
      this.ws.onerror = () => runtimeStore.update({ error: "Connection error" });
      this.ws.onmessage = (event: MessageEvent) => {
        try { const msg: ServerMessage = JSON.parse(event.data); this.handleMessage(msg); } catch {}
      };
    }

    disconnect(): void {
      this.intentionalClose = true;
      if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
      this.ws?.close(); this.ws = null;
      runtimeStore.update({ connected: false, status: "idle" });
    }

    send(msg: ClientMessage): void {
      if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
    }
    sendText(text: string): void { this.send({ type: "user_message", text }); }

    private handleMessage(msg: ServerMessage): void {
      switch (msg.type) {
        case "assistant_message":
          runtimeStore.update({ currentText: msg.text, segments: msg.segments || [] }); break;
        case "assistant_chunk":
          runtimeStore.update({ currentText: msg.text }); break;
        case "character_action":
          runtimeStore.update({ characterAction: { action: msg.action, intensity: msg.intensity || 0.5 } }); break;
        case "tts_audio":
          window.dispatchEvent(new CustomEvent("tts-audio", { detail: msg })); break;
        case "runtime_status":
          runtimeStore.update({ status: msg.status }); break;
        case "error":
          runtimeStore.update({ error: msg.message }); break;
      }
    }

    private scheduleReconnect(): void {
      const delay = RECONNECT_DELAYS[Math.min(this.reconnectAttempt, RECONNECT_DELAYS.length - 1)];
      this.reconnectAttempt++;
      this.reconnectTimer = setTimeout(() => this.connect(), delay);
    }
  }
  export const runtimeClient = new RuntimeClient();

  File 4: src/audio/player.ts
  export class AudioPlayer {
    private ctx: AudioContext | null = null;
    private source: AudioBufferSourceNode | null = null;
    private _playing = false;
    private onDone: (() => void) | null = null;
    get playing(): boolean { return this._playing; }
    private getContext(): AudioContext {
      if (!this.ctx) this.ctx = new AudioContext();
      if (this.ctx.state === "suspended") this.ctx.resume();
      return this.ctx;
    }
    async playBase64(base64: string): Promise<void> {
      this.stop();
      const ctx = this.getContext();
      const binary = atob(base64);
      const array = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) array[i] = binary.charCodeAt(i);
      const buffer = await ctx.decodeAudioData(array.buffer);
      this.source = ctx.createBufferSource();
      this.source.buffer = buffer;
      this.source.connect(ctx.destination);
      this.source.start(0);
      this._playing = true;
      this.source.onended = () => { this._playing = false; this.onDone?.(); };
    }
    stop(): void {
      try { this.source?.stop(); } catch {}
      this.source?.disconnect(); this.source = null; this._playing = false;
    }
    onFinished(cb: () => void): void { this.onDone = cb; }
  }
  export const audioPlayer = new AudioPlayer();

  File 5: src/styles/global.css
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body, #root { width: 100%; height: 100%; overflow: hidden; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f0f1a; color: #fff; }
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #444; border-radius: 3px; }

  Write all 5 files using the Write tool to the correct paths under /c/Users/LENOVO/Desktop/c++/ai/frontend/`,
  subagent_type: "general-purpose",
});

const uiComponents = await agent({
  prompt: `Create the UI component files at C:/Users/LENOVO/Desktop/c++/ai/frontend/src/.

  File 1: src/character/CharacterView.tsx
  import React from "react";
  interface Props { status: string; action: { action: string; intensity: number } | null; }
  export const CharacterView: React.FC<Props> = ({ status, action }) => {
    const getColor = () => {
      switch (status) {
        case "thinking": return "#4A90D9";
        case "speaking": return "#7ED321";
        case "listening": return "#F5A623";
        default: return "#9B9B9B";
      }
    };
    return (
      <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)", position: "relative", overflow: "hidden" }}>
        <div style={{ width: 200, height: 200, borderRadius: "50%", background: getColor(), opacity: action ? 0.5 + action.intensity * 0.5 : 0.7, transition: "all 0.3s ease", boxShadow: "0 0 " + (status === "thinking" ? "60px" : "20px") + " " + getColor() + "66", display: "flex", alignItems: "center", justifyContent: "center", color: "white", fontSize: 48, fontWeight: "bold", animation: status === "thinking" ? "pulse 1.5s ease-in-out infinite" : "none" }}>
          M
        </div>
        <style>{\`@keyframes pulse { 0%,100% { transform: scale(1); } 50% { transform: scale(1.05); } }\`}</style>
      </div>
    );
  };

  File 2: src/conversation/ChatView.tsx
  import React, { useState, useRef, useEffect } from "react";
  interface Message { role: "user" | "assistant"; text: string; id: number; }
  interface Props { messages: Message[]; currentText: string; status: string; onSend: (text: string) => void; onInterrupt: () => void; connected: boolean; }
  export const ChatView: React.FC<Props> = ({ messages, currentText, status, onSend, onInterrupt, connected }) => {
    const [input, setInput] = useState("");
    const bottomRef = useRef<HTMLDivElement>(null);
    useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, currentText]);
    const handleSubmit = (e: React.FormEvent) => { e.preventDefault(); if (!input.trim() || !connected) return; onSend(input.trim()); setInput(""); };
    const isActive = status === "thinking" || status === "speaking";
    return (
      <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#141425" }}>
        <div style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
          {messages.length === 0 && <div style={{ textAlign: "center", color: "#555", marginTop: "40%", fontSize: 14 }}>Start a conversation with Monika</div>}
          {messages.map((m) => (
            <div key={m.id} style={{ marginBottom: 12, textAlign: m.role === "user" ? "right" : "left" }}>
              <div style={{ fontSize: 11, color: "#666", marginBottom: 4 }}>{m.role === "user" ? "You" : "Monika"}</div>
              <span style={{ display: "inline-block", padding: "10px 16px", borderRadius: 16, background: m.role === "user" ? "#4A90D9" : "#2D2D3F", color: "#fff", maxWidth: "80%", fontSize: 14, lineHeight: 1.5 }}>{m.text}</span>
            </div>
          ))}
          {currentText && (
            <div style={{ textAlign: "left", marginBottom: 12 }}>
              <div style={{ fontSize: 11, color: "#666", marginBottom: 4 }}>Monika</div>
              <span style={{ display: "inline-block", padding: "10px 16px", borderRadius: 16, background: "#2D2D3F", color: "#aaa", maxWidth: "80%", fontSize: 14, fontStyle: "italic" }}>{currentText}</span>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
        <div style={{ padding: "12px 16px", borderTop: "1px solid #2a2a3a" }}>
          <div style={{ marginBottom: 8, display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: "#888" }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: !connected ? "#ff4444" : status === "thinking" ? "#F5A623" : status === "speaking" ? "#7ED321" : "#4A90D9", display: "inline-block", transition: "background 0.3s" }} />
            {connected ? "Runtime: " + status : "Disconnected"}
            {isActive && <button onClick={onInterrupt} style={{ marginLeft: "auto", background: "transparent", border: "1px solid #ff4444", color: "#ff4444", borderRadius: 4, padding: "2px 10px", cursor: "pointer", fontSize: 12 }}>Interrupt</button>}
          </div>
          <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8 }}>
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={connected ? "Message Monika..." : "Connecting..."} disabled={!connected} style={{ flex: 1, padding: "10px 14px", borderRadius: 8, border: "1px solid #333", background: "#0f0f1a", color: "#fff", fontSize: 14, outline: "none" }} />
            <button type="submit" disabled={!connected || !input.trim()} style={{ padding: "10px 24px", borderRadius: 8, border: "none", background: connected ? "#4A90D9" : "#333", color: "#fff", cursor: connected ? "pointer" : "not-allowed", fontSize: 14, fontWeight: 600 }}>Send</button>
          </form>
        </div>
      </div>
    );
  };

  File 3: src/App.tsx
  import React, { useEffect, useState, useRef } from "react";
  import { runtimeClient } from "./runtime/client";
  import { runtimeStore } from "./runtime/state";
  import type { RuntimeState } from "./runtime/state";
  import { CharacterView } from "./character/CharacterView";
  import { ChatView } from "./conversation/ChatView";
  import { audioPlayer } from "./audio/player";

  interface Message { role: "user" | "assistant"; text: string; id: number; }
  let msgId = 0;

  export const App: React.FC = () => {
    const [state, setState] = useState<RuntimeState>(runtimeStore.getState());
    const [messages, setMessages] = useState<Message[]>([]);
    const prevStatusRef = useRef(state.status);

    useEffect(() => { const unsub = runtimeStore.subscribe(setState); return unsub; }, []);
    useEffect(() => {
      const handler = (e: Event) => { const d = (e as CustomEvent).detail; if (d.data) audioPlayer.playBase64(d.data); };
      window.addEventListener("tts-audio", handler);
      return () => window.removeEventListener("tts-audio", handler);
    }, []);
    useEffect(() => { runtimeClient.connect(); return () => runtimeClient.disconnect(); }, []);

    useEffect(() => {
      const prev = prevStatusRef.current;
      prevStatusRef.current = state.status;
      if (prev === "speaking" && state.status === "idle" && state.currentText) {
        setMessages((p) => [...p, { role: "assistant", text: state.currentText, id: ++msgId }]);
        runtimeStore.update({ currentText: "" });
      }
    }, [state.status, state.currentText]);

    const handleSend = (text: string) => {
      setMessages((p) => [...p, { role: "user", text, id: ++msgId }]);
      runtimeClient.sendText(text);
    };
    const handleInterrupt = () => { audioPlayer.stop(); runtimeClient.send({ type: "interrupt" }); };

    return (
      <div style={{ display: "flex", width: "100%", height: "100%" }}>
        <div style={{ width: "40%", height: "100%", flexShrink: 0 }}>
          <CharacterView status={state.status} action={state.characterAction} />
        </div>
        <div style={{ width: "60%", height: "100%", flexShrink: 0 }}>
          <ChatView messages={messages} currentText={state.currentText} status={state.status} onSend={handleSend} onInterrupt={handleInterrupt} connected={state.connected} />
        </div>
      </div>
    );
  };

  File 4: src/main.tsx
  import React from "react";
  import ReactDOM from "react-dom/client";
  import { App } from "./App";
  import "./styles/global.css";
  ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);

  Write all 4 files using the Write tool to correct paths.`,
  subagent_type: "general-purpose",
});

const buildResult = await agent({
  prompt: `Build the new frontend and fix any errors.

  cd /c/Users/LENOVO/Desktop/c++/ai/frontend

  First check all files exist: ls -la src/runtime/ src/character/ src/conversation/ src/audio/ src/styles/ src/App.tsx src/main.tsx index.html package.json vite.config.ts tsconfig.json 2>&1

  If any file is missing, report which and stop.

  Run: npx tsc --noEmit 2>&1
  If errors, fix the source files and retry until clean.

  Then run: npm run build 2>&1

  Finally: ls -la dist/ 2>&1

  Report: build success or failure. If failed, include the exact error.`,
  subagent_type: "general-purpose",
});

return { webSdkCheck, deleteOld, scaffold, runtimeLayer, uiComponents, buildResult };
