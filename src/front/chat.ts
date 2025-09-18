import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { marked } from "marked";
import DOMPurify from "dompurify";

type Role = "user" | "assistant";
type Msg = {
  id: string;
  role: Role;
  content: string;
  pending?: boolean;
  error?: string;
};

const h = React.createElement;

const API_URL = "https://fenyo.net/MES/api/chat";
const USER_URL = "https://fenyo.net/MES/api/user";

function uid(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function useAutoScroll(dep: any) {
  const ref = useRef<HTMLUListElement | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [dep]);
  return ref;
}

function IconSend(props: { size?: number }) {
  const size = props.size ?? 16;
  return h(
    "svg",
    { width: size, height: size, viewBox: "0 0 24 24", fill: "none", xmlns: "http://www.w3.org/2000/svg" },
    h("path", { d: "M3 11L21 3L13 21L11 13L3 11Z", stroke: "currentColor", strokeWidth: 2, fill: "currentColor", opacity: 0.95 })
  );
}

function TypingDots() {
  return h(
    "span",
    { className: "typing" },
    h("span", { className: "dot" }),
    h("span", { className: "dot" }),
    h("span", { className: "dot" })
  );
}

function MessageView({ msg, userName }: { msg: Msg; userName: string }) {
  const isAssistant = msg.role === "assistant";
  const html = isAssistant
    ? DOMPurify.sanitize((marked.parse(msg.content || "") as string) || "")
    : "";

  return h(
    "li",
    { className: `message ${msg.role}` },
    h(
      "div",
      { className: "avatar", title: isAssistant ? "Assistant" : (userName || "Vous") },
      isAssistant ? h("img", { src: "/MES/favicon.png", alt: "Assistant" }) : (userName || "VO")
    ),
    h(
      "div",
      { className: "bubble" },
      isAssistant
        ? (msg.pending && !msg.content
            ? h(TypingDots)
            : h("div", { dangerouslySetInnerHTML: { __html: html } }))
        : msg.content,
      msg.error ? h("div", { className: "meta" }, "Erreur: ", msg.error) : null
    )
  );
}

function Header() {
  return h(
    "header",
    { className: "chat-header" },
    h("div", { className: "logo", "aria-hidden": true }, "DT"),
    h(
      "div",
      { className: "title" },
      h("strong", null, "Assistant IA de la Direction Technique"),
      h("span", null, "Posez vos questions, j’y réponds en quelques secondes.")
    )
  );
}

async function sendToApi(
  history: Msg[],
  onDelta: (text: string) => void
): Promise<void> {
  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        // Envoie tous les messages (user et assistant) dans l'ordre de création,
        // en ignorant les messages vides (ex: placeholders en cours).
        messages: history
          .filter(m => (m.role === "user" || m.role === "assistant") && typeof m.content === "string" && m.content.length > 0)
          .map(({ role, content }) => ({ role, content }))
      }),
    });
    if (!res.ok) {
      const e = new Error(`HTTP ${res.status} ${res.statusText}`);
      (e as any).url = API_URL;
      throw e;
    }
    const reader = res.body?.getReader();
    if (!reader) {
      const e = new Error("Flux de réponse indisponible");
      (e as any).url = API_URL;
      throw e;
    }
    const decoder = new TextDecoder();
    let buffer = "";

    // Lecture incrémentale des lignes NDJSON
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let idx: number;
      // Traite toutes les lignes complètes disponibles
      while ((idx = buffer.indexOf("\n")) !== -1) {
        const raw = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 1);
        if (!raw) continue;
        let obj: any;
        try {
          obj = JSON.parse(raw);
        } catch {
          continue;
        }
        // Supporte à la fois l'ancien format (/api/generate) et le nouveau format chat d'Ollama
        if (obj?.done === true) {
          try { await reader.cancel(); } catch {}
          return;
        }
        if (obj && typeof obj?.message?.content === "string" && obj.message.content) {
          onDelta(obj.message.content as string);
        }
      }
    }
  } catch (err: any) {
    const e = err instanceof Error ? err : new Error(String(err));
    (e as any).url = (e as any).url || API_URL;
    throw e;
  }
}

function ChatApp() {
  const [messages, setMessages] = useState<Msg[]>(() => []);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [userName, setUserName] = useState<string>("VO");
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await fetch(USER_URL, { method: "GET" });
        if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
        const data = await res.json().catch(() => ({} as any));
        const name = (data && ((data as any).USER ?? (data as any).user ?? (data as any).name)) || "";
        if (alive) setUserName(name || "VO");
      } catch (_e) {
        if (alive) setUserName("VO");
      }
    })();
    return () => { alive = false; };
  }, []);

  const listRef = useAutoScroll(messages);

  const canSend = useMemo(() => input.trim().length > 0 && !sending, [input, sending]);

  async function handleSend() {
    const text = input.trim();
    if (!text || sending) return;
    setSending(true);

    const userMsg: Msg = { id: uid(), role: "user", content: text };
    const pending: Msg = { id: uid(), role: "assistant", content: "", pending: true };

    setMessages(prev => [...prev, userMsg, pending]);
    setInput("");

    try {
      await sendToApi(
        [...messages, userMsg],
        (delta) => {
          setMessages(prev =>
            prev.map(m =>
              m.id === pending.id ? { ...m, content: m.content + delta } : m
            )
          );
        }
      );
      setMessages(prev =>
        prev.map(m => (m.id === pending.id ? { ...m, pending: false } : m))
      );
    } catch (err: any) {
      const url = (err && err.url) || API_URL;
      const msg = err?.message ? String(err.message) : String(err);
      setMessages(prev =>
        prev.map(m =>
          m.id === pending.id
            ? {
                ...m,
                pending: false,
                error: `URL: ${url} — Erreur: ${msg}`,
              }
            : m
        )
      );
    } finally {
      setSending(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (canSend) void handleSend();
    }
  }

  return h(
    "div",
    { className: "chat-app" },
    h(Header),
    h(
      "main",
      { className: "chat-body" },
      h(
        "ul",
        { className: "messages", ref: listRef },
        messages.map(m => h(MessageView, { key: m.id, msg: m, userName }))
      )
    ),
    h(
      "footer",
      { className: "chat-input" },
      h("div", { className: "toolbar" }, h("div", null, "Appuyez sur Entrée pour envoyer • Shift+Entrée pour une nouvelle ligne")),
      h(
        "div",
        { className: "composer" },
        h("textarea", {
          placeholder: "Écrivez votre message…",
          value: input,
          onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => setInput(e.target.value),
          onKeyDown,
          "aria-label": "Champ de saisie du message",
        }),
        h(
          "button",
          { className: "button", onClick: () => void handleSend(), disabled: !canSend, title: "Envoyer (Entrée)" },
          h(IconSend, { size: 16 }),
          " Envoyer"
        )
      ),
      h("div", { className: "helper" }, sending ? "L’assistant rédige une réponse…" : "\u00A0")
    )
  );
}

// Mount
const rootEl = document.getElementById("root");
if (rootEl) {
  const root = createRoot(rootEl);
  root.render(h(ChatApp));
}
