import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

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
  return h(
    "li",
    { className: `message ${msg.role}` },
    h(
      "div",
      { className: "avatar", title: msg.role === "user" ? (userName || "Vous") : "Assistant" },
      msg.role === "user" ? (userName || "VO") : h("img", { src: "/MES/favicon.png", alt: "Assistant" })
    ),
    h(
      "div",
      { className: "bubble" },
      msg.pending ? h(TypingDots) : msg.content,
      msg.error ? h("div", { className: "meta" }, "Erreur: ", msg.error) : null
    )
  );
}

function Header() {
  return h(
    "header",
    { className: "chat-header" },
    h("div", { className: "logo", "aria-hidden": true }, "MES"),
    h(
      "div",
      { className: "title" },
      h("strong", null, "Assistant IA de la Direction Technique CNAM du projet Mon Espace Santé et du DMP"),
      h("span", null, "Posez vos questions, j’y réponds en quelques secondes.")
    )
  );
}

async function sendToApi(history: Msg[]): Promise<string> {
  // Essaie un endpoint standard JSON: { messages: [{role, content}, ...] } -> { reply: string }
  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: history.map(({ role, content }) => ({ role, content })),
      }),
    });
    if (!res.ok) {
      const e = new Error(`HTTP ${res.status} ${res.statusText}`);
      (e as any).url = API_URL;
      throw e;
    }
    // Accepte plusieurs formats courants
    const textCT = res.headers.get("content-type") || "";
    if (textCT.includes("application/json")) {
      const data = await res.json();
      if (typeof data?.reply === "string") return data.reply;
      const gpt = data?.choices?.[0]?.message?.content;
      if (typeof gpt === "string") return gpt;
      if (typeof data?.content === "string") return data.content;
      if (typeof data?.text === "string") return data.text;
      // fallback sur JSON inconnu
      return JSON.stringify(data);
    } else {
      return await res.text();
    }
  } catch (err: any) {
    const e = err instanceof Error ? err : new Error(String(err));
    (e as any).url = (e as any).url || API_URL;
    throw e;
  }
}

function ChatApp() {
  const [messages, setMessages] = useState<Msg[]>(() => [
    {
      id: uid(),
      role: "assistant",
      content: "Bonjour ! Je suis votre assistant IA. Comment puis-je vous aider aujourd’hui ?",
    },
  ]);
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
      const reply = await sendToApi([...messages, userMsg]);
      setMessages(prev =>
        prev.map(m => (m.id === pending.id ? { ...m, content: reply, pending: false } : m))
      );
    } catch (err: any) {
      const url = (err && err.url) || API_URL;
      const msg = err?.message ? String(err.message) : String(err);
      setMessages(prev =>
        prev.map(m =>
          m.id === pending.id
            ? {
                ...m,
                content: "Impossible de contacter le serveur.",
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
