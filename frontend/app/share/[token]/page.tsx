import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";

interface Source {
  title:       string;
  url:         string | null;
  source_type: string;
  year:        number | null;
  score:       number;
}

const SOURCE_LABELS: Record<string, string> = {
  legislation:     "Ustawa",
  judgment_nsa:    "NSA/WSA",
  judgment_sn:     "SN",
  judgment_tk:     "TK",
  judgment_common: "Sąd powszechny",
  judgment_kio:    "KIO",
};

function formatDate(d: Date) {
  return d.toLocaleDateString("pl-PL", { day: "2-digit", month: "long", year: "numeric" });
}

export default async function SharePage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const report = await prisma.sharedReport.findUnique({ where: { token } });

  if (!report) notFound();
  if (report.expiresAt && report.expiresAt < new Date()) notFound();

  let sources: Source[] = [];
  try { sources = JSON.parse(report.sources) as Source[]; } catch { /* empty */ }

  // Escape HTML then inject only safe <sup> citation badges
  const answerEscaped = report.answer
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  const answerWithCitations = answerEscaped.replace(
    /\[(\d+)\]/g,
    (_m, n) => `<sup class="citation">[${n}]</sup>`,
  );

  return (
    <div className="min-h-screen bg-slate-50" style={{ fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>
      {/* Header */}
      <header style={{ background: "linear-gradient(135deg,#1d4ed8,#2563eb)", padding: "20px 24px" }}>
        <div style={{ maxWidth: 720, margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <a href="/" style={{ color: "#fff", textDecoration: "none", fontSize: 20, fontWeight: 700 }}>
            <span style={{ opacity: 0.7 }}>Lex</span>Corpus
          </a>
          <span style={{ color: "#bfdbfe", fontSize: 13 }}>
            {formatDate(report.createdAt)}
            {report.expiresAt && ` · wygasa ${formatDate(report.expiresAt)}`}
          </span>
        </div>
      </header>

      <main style={{ maxWidth: 720, margin: "0 auto", padding: "32px 24px" }}>
        {/* Question */}
        <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #e2e8f0", padding: "24px 28px", marginBottom: 20 }}>
          <p style={{ fontSize: 11, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
            Pytanie
          </p>
          <p style={{ fontSize: 17, fontWeight: 600, color: "#0f172a", lineHeight: 1.5, margin: 0 }}>
            {report.question}
          </p>
        </div>

        {/* Answer */}
        <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #e2e8f0", padding: "24px 28px", marginBottom: 20 }}>
          <p style={{ fontSize: 11, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>
            Odpowiedź AI · {report.modelUsed}
          </p>
          <div
            style={{ fontSize: 15, color: "#1e293b", lineHeight: 1.75 }}
            dangerouslySetInnerHTML={{ __html: answerWithCitations }}
          />
        </div>

        {/* Sources */}
        {sources.length > 0 && (
          <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #e2e8f0", padding: "24px 28px", marginBottom: 20 }}>
            <p style={{ fontSize: 11, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>
              Źródła ({sources.length})
            </p>
            <ol style={{ margin: 0, paddingLeft: 20 }}>
              {sources.map((s, i) => (
                <li key={i} style={{ marginBottom: 10 }}>
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                    <span style={{
                      background: "#eff6ff", color: "#1d4ed8", fontSize: 11,
                      padding: "2px 8px", borderRadius: 20, fontWeight: 600, whiteSpace: "nowrap", flexShrink: 0,
                    }}>
                      {SOURCE_LABELS[s.source_type] ?? s.source_type}{s.year ? ` · ${s.year}` : ""}
                    </span>
                    <div>
                      {s.url ? (
                        <a href={s.url} target="_blank" rel="noopener noreferrer"
                           style={{ color: "#2563eb", textDecoration: "none", fontSize: 13 }}>
                          {s.title}
                        </a>
                      ) : (
                        <span style={{ color: "#475569", fontSize: 13 }}>{s.title}</span>
                      )}
                      <span style={{ color: "#94a3b8", fontSize: 11, marginLeft: 8 }}>
                        {Math.round(s.score * 100)}% dopasowania
                      </span>
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        )}

        {/* Footer */}
        <div style={{ textAlign: "center", padding: "16px 0" }}>
          <p style={{ fontSize: 12, color: "#94a3b8", margin: "0 0 8px" }}>
            Odpowiedź wygenerowana przez AI. Nie stanowi porady prawnej.
          </p>
          <a href="/ask" style={{ fontSize: 13, color: "#2563eb", textDecoration: "none" }}>
            Zadaj własne pytanie w LexCorpus →
          </a>
        </div>
      </main>

      <style>{`
        .citation { color: #2563eb; font-size: 0.7em; vertical-align: super; font-weight: 600; }
      `}</style>
    </div>
  );
}
