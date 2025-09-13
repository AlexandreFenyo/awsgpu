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

function MessageView({ msg }: { msg: Msg }) {
  return h(
    "li",
    { className: `message ${msg.role}` },
    h("div", { className: "avatar", title: msg.role === "user" ? "Vous" : "Assistant" }, msg.role === "user" ? "VO" : "AI"),
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
    h("div", { className: "logo", "aria-hidden": true }, "AI"),
    h(
      "div",
      { className: "title" },
      h("strong", null, "Assistant IA"),
      h("span", null, "Posez vos questions, j’y réponds en quelques secondes.")
    )
  );
}

async function sendToApi(history: Msg[]): Promise<string> {
  // Essaie un endpoint standard JSON: { messages: [{role, content}, ...] } -> { reply: string }
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: history.map(({ role, content }) => ({ role, content })),
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
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
  } catch (_err) {
    // Fallback simulé pour une démo offline
    const last = history.filter(m => m.role === "user").slice(-1)[0];
    const echo = last?.content ?? "Bonjour";
    await new Promise(r => setTimeout(r, 650));
    return `Je n’ai pas pu contacter le serveur.\nRéponse simulée: "${echo}"`;
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
      setMessages(prev =>
        prev.map(m =>
          m.id === pending.id ? { ...m, content: "Oups, une erreur est survenue.", pending: false, error: String(err?.message || err) } : m
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
        messages.map(m => h(MessageView, { key: m.id, msg: m }))
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
