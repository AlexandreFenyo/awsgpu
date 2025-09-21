import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { marked } from "marked";
import DOMPurify from "dompurify";

type Role = "user" | "assistant" | "tool";
type Msg = {
  id: string;
  role: Role;
  content: string;
  thinking?: string;
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
  const thinkingHtml = isAssistant
    ? DOMPurify.sanitize((marked.parse(msg.thinking || "") as string) || "")
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
        ? (msg.pending
            ? (msg.content
                ? h("div", { dangerouslySetInnerHTML: { __html: html } })
                : (msg.thinking && msg.thinking.length > 0
                    ? h(
                        "div",
                        { style: { color: "#888" } },
                        "Thinking: ",
                        h("div", { dangerouslySetInnerHTML: { __html: thinkingHtml } })
                      )
                    : h(TypingDots)))
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
  serverHistory: any[],
  newUserText: string,
  onServerMessages: (msgs: any[]) => void,
  onThinking: (delta: string, append: boolean) => void,
  onDelta: (text: string) => void,
  onDone: (assistantText: string, msgsFromServer: any[]) => void,
  onPromptEvalCount?: (count: number) => void
): Promise<void> {
  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        // Envoie les messages précédemment validés par le serveur (inchangés),
        // puis le nouveau message utilisateur saisi.
        messages: [
          ...serverHistory,
          { role: "user", content: newUserText }
        ]
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
    let assistantFull = "";
    let assistantThinking = "";
    let msgsFromServer: any[] | null = null;
    let ignoreNextDoneBecauseOfToolCall = false;

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
        // Réception des messages utilisés (avant le flux de génération)
        if (Array.isArray(obj?.messages)) {
          const arr = obj.messages as any[];
          msgsFromServer = arr;
          onServerMessages(arr);
          continue;
        }
        // Capture prompt_eval_count s'il est présent
        if (typeof obj?.prompt_eval_count === "number") {
          onPromptEvalCount?.(obj.prompt_eval_count as number);
        }
        // Flux de génération chat d'Ollama
        // 1) Traiter d'abord les deltas de message (certains modèles n'envoient le contenu qu'à la dernière ligne done:true)
        if (obj) {
          // Extraire les deltas possibles selon les variantes d'Ollama
          let c = "";
          let t = "";
          const m: any = obj.message;
          let hadToolCalls = false;
          if (m && typeof m === "object") {
            if (typeof m.content === "string") c = m.content;
            else if (m.delta && typeof m.delta.content === "string") c = m.delta.content;
            if (typeof m.thinking === "string") t = m.thinking;
            else if (m.delta && typeof m.delta.thinking === "string") t = m.delta.thinking;
            // Si l'assistant demande un outil, ignorer le prochain done:true (fin de première étape)
            if (Array.isArray((m as any).tool_calls) && (m as any).tool_calls.length > 0) {
              ignoreNextDoneBecauseOfToolCall = true;
              hadToolCalls = true;
            }
          }
          // Par sécurité, si tool_calls est au niveau racine (cas atypique), appliquer la même logique
          if (!hadToolCalls && Array.isArray((obj as any).tool_calls) && (obj as any).tool_calls.length > 0) {
            ignoreNextDoneBecauseOfToolCall = true;
            hadToolCalls = true;
          }
          // Certains builds d'Ollama émettent les deltas au niveau racine.
          if (!c && obj.delta && typeof obj.delta.content === "string") c = obj.delta.content;
          if (!t && obj.delta && typeof obj.delta.thinking === "string") t = obj.delta.thinking;

          if (!c && typeof obj.response === "string") c = obj.response;
          if (!c && typeof obj.content === "string") c = obj.content;
          if (!t && typeof obj.thinking === "string") t = obj.thinking;

          // Si Ollama "réfléchit", il envoie thinking (delta) et content vide.
          if (t && !c) {
            assistantThinking += t;
            onThinking(t, true); // append
          }

          // Dès qu'on reçoit du contenu (réponse), on efface la réflexion affichée.
          if (c) {
            if (assistantThinking) {
              assistantThinking = "";
              onThinking("", false); // clear
            }
            const delta = c;
            assistantFull += delta;
            onDelta(delta);
          }
        }
        // 2) Puis gérer le signal de fin. Ainsi, si le contenu n'arrive qu'à la dernière ligne (done:true),
        // on l'a déjà intégré dans assistantFull avant de terminer.
        if (obj?.done === true) {
          if (ignoreNextDoneBecauseOfToolCall) {
            // Première étape terminée (tool-call). On attend la suite du flux avec les résultats de l'outil.
            ignoreNextDoneBecauseOfToolCall = false;
          } else {
            onDone(assistantFull, msgsFromServer ?? [...serverHistory, { role: "user", content: newUserText }]);
            // Ne pas annuler explicitement le flux côté navigateur pour éviter NS_BASE_STREAM_CLOSED.
            // On laisse le serveur fermer proprement le flux.
            return;
          }
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
  const [serverHistory, setServerHistory] = useState<any[]>(() => []);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [userName, setUserName] = useState<string>("VO");
  const [promptEvalCount, setPromptEvalCount] = useState<number>(0);

  // À chaque rechargement, on repart de zéro pour l'historique envoyé au serveur
  useEffect(() => {
    try { localStorage.removeItem("serverHistory"); } catch {}
    try { sessionStorage.removeItem("serverHistory"); } catch {}
    setServerHistory([]);
  }, []);

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
        serverHistory,
        text,
        (msgsForServer) => {
          setServerHistory(msgsForServer);
        },
        (thinkingDelta, append) => {
          setMessages(prev =>
            prev.map(m =>
              m.id === pending.id
                ? { ...m, thinking: append ? ((m.thinking || "") + thinkingDelta) : "" }
                : m
            )
          );
        },
        (delta) => {
          setMessages(prev =>
            prev.map(m =>
              m.id === pending.id ? { ...m, content: m.content + delta } : m
            )
          );
        },
        (assistantText, msgsForServer) => {
          const arr = Array.isArray(msgsForServer) ? msgsForServer : [];
          const last = arr.length > 0 ? arr[arr.length - 1] : null;
          if (last && typeof last === "object" && (last as any).role === "assistant") {
            // Le serveur a déjà inclus le dernier message assistant (ex: tool_calls sans tools activés)
            setServerHistory(arr);
          } else {
            setServerHistory([...arr, { role: "assistant", content: assistantText }]);
          }
        },
        (count) => {
          setPromptEvalCount(count);
        }
      );
      setMessages(prev =>
        prev.map(m => (m.id === pending.id ? { ...m, pending: false, thinking: "" } : m))
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
      h(
        "div",
        { className: "toolbar" },
        h(
          "div",
          null,
          `Appuyez sur Entrée pour envoyer • Shift+Entrée pour une nouvelle ligne • Contexte courant : ${promptEvalCount} ${promptEvalCount === 0 ? "/ 131072 tokens" : "/ 131072 tokens"}`
        )
      ),
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
