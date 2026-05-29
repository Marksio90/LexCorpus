"use client";

import { useState, useRef, useEffect } from "react";

interface Message {
  role:    "user" | "assistant";
  content: string;
  sources?: { title: string; url: string | null; score: number }[];
}

interface Props {
  token:       string;
  title:       string;
  welcomeMsg:  string;
  accentColor: string;
  logoUrl:     string | null;
}

export default function WidgetChat({ token, title, welcomeMsg, accentColor, logoUrl }: Props) {
  const [messages,  setMessages]  = useState<Message[]>([
    { role: "assistant", content: welcomeMsg },
  ]);
  const [input,     setInput]     = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef  = useRef<HTMLDivElement>(null);
  const inputRef   = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    const q = input.trim();
    if (!q || streaming) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: q }]);
    setStreaming(true);

    const assistantIdx = messages.length + 1;
    setMessages((m) => [...m, { role: "assistant", content: "" }]);

    try {
      const res = await fetch(`/api/widget/${token}/ask`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ question: q }),
      });

      if (!res.ok) {
        setMessages((m) => {
          const copy = [...m];
          copy[assistantIdx] = { role: "assistant", content: "Przepraszam, wystąpił błąd. Spróbuj ponownie." };
          return copy;
        });
        setStreaming(false);
        return;
      }

      const reader  = res.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let answer = "";
      const sources: Message["sources"] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n\n");
        buf = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = JSON.parse(line.slice(6)) as {
            type?: string; delta?: string; sources?: typeof sources;
          };
          if (data.type === "sources" && data.sources) {
            sources.push(...data.sources.slice(0, 3));
          }
          if (data.delta) {
            answer += data.delta;
            setMessages((m) => {
              const copy = [...m];
              copy[assistantIdx] = { role: "assistant", content: answer, sources };
              return copy;
            });
          }
        }
      }
    } catch {
      setMessages((m) => {
        const copy = [...m];
        copy[assistantIdx] = { role: "assistant", content: "Przepraszam, wystąpił błąd." };
        return copy;
      });
    } finally {
      setStreaming(false);
      inputRef.current?.focus();
    }
  }

  const accent = accentColor || "#2563eb";

  return (
    <div
      style={{ fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}
      className="flex flex-col h-screen bg-white"
    >
      {/* Header */}
      <div
        style={{ background: accent }}
        className="flex items-center gap-3 px-4 py-3 shrink-0"
      >
        {logoUrl && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={logoUrl} alt="logo" className="h-7 w-7 rounded-full object-cover bg-white/20" />
        )}
        <span className="text-white font-semibold text-sm">{title}</span>
        <span className="ml-auto text-white/60 text-xs">powered by LexCorpus</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className="max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed"
              style={
                msg.role === "user"
                  ? { background: accent, color: "#fff" }
                  : { background: "#f1f5f9", color: "#1e293b" }
              }
            >
              {msg.content || (streaming && i === messages.length - 1 ? (
                <span className="inline-flex gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: "300ms" }} />
                </span>
              ) : "")}
              {/* Sources */}
              {msg.sources && msg.sources.length > 0 && (
                <div className="mt-2 pt-2 border-t border-slate-200 space-y-0.5">
                  {msg.sources.map((s, si) => (
                    <div key={si} className="text-xs text-slate-500">
                      {s.url ? (
                        <a href={s.url} target="_blank" rel="noopener noreferrer" className="underline hover:text-slate-700">
                          [{si + 1}] {s.title}
                        </a>
                      ) : (
                        <span>[{si + 1}] {s.title}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-slate-200 px-3 py-3 flex gap-2">
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } }}
          placeholder="Zadaj pytanie prawne…"
          disabled={streaming}
          className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-xl focus:outline-none focus:ring-2 disabled:opacity-50 bg-white"
          style={{ "--tw-ring-color": accent } as React.CSSProperties}
        />
        <button
          onClick={send}
          disabled={streaming || !input.trim()}
          style={{ background: accent }}
          className="px-4 py-2 text-white text-sm font-medium rounded-xl disabled:opacity-40 transition-opacity"
        >
          ↑
        </button>
      </div>
    </div>
  );
}
