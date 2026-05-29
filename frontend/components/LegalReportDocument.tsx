/**
 * LegalReportDocument — szablon PDF raportu prawnego.
 * Renderowany wyłącznie client-side przez @react-pdf/renderer.
 */
import {
  Document, Page, Text, View, StyleSheet, Link, Font,
} from "@react-pdf/renderer";
import type { AskResponse, SourceDocument } from "@/lib/types";

// ── Style ────────────────────────────────────────────────────────────────────

const S = StyleSheet.create({
  page: {
    fontFamily:    "Helvetica",
    fontSize:      10,
    color:         "#1e293b",
    paddingTop:    48,
    paddingBottom: 56,
    paddingLeft:   56,
    paddingRight:  56,
    lineHeight:    1.5,
  },
  // Header
  header: {
    flexDirection:  "row",
    justifyContent: "space-between",
    alignItems:     "flex-end",
    marginBottom:   28,
    paddingBottom:  10,
    borderBottomWidth: 1,
    borderBottomColor: "#2563eb",
    borderBottomStyle: "solid",
  },
  brand: { fontSize: 14, fontFamily: "Helvetica-Bold", color: "#2563eb" },
  meta:  { fontSize: 8,  color: "#94a3b8", textAlign: "right" },
  // Sections
  sectionLabel: {
    fontSize:      7,
    fontFamily:    "Helvetica-Bold",
    letterSpacing: 1,
    color:         "#64748b",
    textTransform: "uppercase",
    marginBottom:  4,
  },
  question: {
    fontSize:    13,
    fontFamily:  "Helvetica-Bold",
    color:       "#0f172a",
    marginBottom: 20,
    lineHeight:  1.4,
  },
  divider: {
    borderBottomWidth: 1,
    borderBottomColor: "#e2e8f0",
    borderBottomStyle: "solid",
    marginVertical:    16,
  },
  answerBlock: {
    marginBottom: 6,
  },
  paragraph: {
    marginBottom: 8,
    lineHeight:   1.6,
  },
  // Sources
  sourceItem: {
    marginBottom:   8,
    paddingLeft:    10,
    borderLeftWidth: 2,
    borderLeftColor: "#2563eb",
    borderLeftStyle: "solid",
  },
  sourceTitle: { fontFamily: "Helvetica-Bold", fontSize: 9, color: "#1e293b" },
  sourceMeta:  { fontSize: 8, color: "#64748b", marginTop: 1 },
  sourceLink:  { fontSize: 8, color: "#2563eb", marginTop: 2 },
  badge: {
    fontSize:        7,
    color:           "#1d4ed8",
    backgroundColor: "#eff6ff",
    paddingHorizontal: 4,
    paddingVertical: 2,
    borderRadius:    3,
  },
  // Footer
  footer: {
    position:   "absolute",
    bottom:     28,
    left:       56,
    right:      56,
    flexDirection:  "row",
    justifyContent: "space-between",
    fontSize:   8,
    color:      "#94a3b8",
    borderTopWidth: 1,
    borderTopColor: "#e2e8f0",
    borderTopStyle: "solid",
    paddingTop: 6,
  },
  disclaimer: {
    fontSize:      7.5,
    color:         "#94a3b8",
    marginTop:     20,
    paddingTop:    12,
    borderTopWidth: 1,
    borderTopColor: "#e2e8f0",
    borderTopStyle: "solid",
    lineHeight:    1.5,
  },
});

// ── Source type labels ────────────────────────────────────────────────────────

const SOURCE_LABELS: Record<string, string> = {
  legislation:    "Ustawa/Rozporządzenie",
  judgment_nsa:   "Wyrok NSA/WSA",
  judgment_sn:    "Wyrok SN",
  judgment_tk:    "Wyrok TK",
  judgment_common:"Wyrok sądu powszechnego",
  judgment_kio:   "Wyrok KIO",
  unknown:        "Dokument",
};

function externalUrl(source: SourceDocument): string | null {
  if (source.source_type === "legislation" && source.year && source.pos) {
    const year = String(source.year).padStart(4, "0");
    const pos  = String(source.pos).padStart(7, "0");
    return `https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU${year}${pos}`;
  }
  if (source.url) return source.url;
  return null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function splitParagraphs(text: string): string[] {
  return text.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);
}

// Citation badges [1], [2] → inline text "(źródło N)"
function stripCitations(text: string): string {
  return text.replace(/\[(\d+)\]/g, "(źródło $1)");
}

// ── Document component ────────────────────────────────────────────────────────

interface Props {
  response:  AskResponse;
  createdAt: string;   // ISO string
}

export function LegalReportDocument({ response, createdAt }: Props) {
  const { question, answer, sources, model_used } = response;
  const dateStr = new Date(createdAt).toLocaleString("pl-PL", {
    day: "2-digit", month: "long", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });

  const paragraphs = splitParagraphs(answer);

  return (
    <Document
      title={`LexCorpus — ${question.slice(0, 80)}`}
      author="LexCorpus"
      subject="Raport prawny"
      keywords="prawo, ISAP, SAOS, Polska"
    >
      <Page size="A4" style={S.page}>

        {/* Header */}
        <View style={S.header}>
          <Text style={S.brand}>LexCorpus</Text>
          <View>
            <Text style={S.meta}>Raport prawny</Text>
            <Text style={S.meta}>{dateStr}</Text>
            <Text style={S.meta}>Model: {model_used}</Text>
          </View>
        </View>

        {/* Question */}
        <Text style={S.sectionLabel}>Pytanie</Text>
        <Text style={S.question}>{question}</Text>

        <View style={S.divider} />

        {/* Answer */}
        <Text style={S.sectionLabel}>Odpowiedź</Text>
        <View style={S.answerBlock}>
          {paragraphs.map((para, i) => (
            <Text key={i} style={S.paragraph}>
              {stripCitations(para)}
            </Text>
          ))}
        </View>

        {/* Sources */}
        {sources.length > 0 && (
          <>
            <View style={S.divider} />
            <Text style={S.sectionLabel}>Źródła ({sources.length})</Text>
            {sources.map((src, i) => {
              const url = externalUrl(src);
              return (
                <View key={i} style={S.sourceItem}>
                  <Text style={S.sourceTitle}>
                    [{i + 1}] {src.title}
                  </Text>
                  <Text style={S.sourceMeta}>
                    {SOURCE_LABELS[src.source_type] ?? "Dokument"}
                    {src.year ? ` · ${src.year}` : ""}
                    {src.score ? ` · trafność: ${(src.score * 100).toFixed(0)}%` : ""}
                  </Text>
                  {url && (
                    <Link src={url} style={S.sourceLink}>{url}</Link>
                  )}
                </View>
              );
            })}
          </>
        )}

        {/* Disclaimer */}
        <Text style={S.disclaimer}>
          Niniejszy raport został wygenerowany automatycznie przez system LexCorpus na podstawie
          dokumentów z baz ISAP i SAOS. Nie stanowi porady prawnej. W sprawach wymagających
          indywidualnej oceny skonsultuj się z radcą prawnym lub adwokatem.
        </Text>

        {/* Footer */}
        <View style={S.footer} fixed>
          <Text>lexcorpus.pl</Text>
          <Text render={({ pageNumber, totalPages }) => `${pageNumber} / ${totalPages}`} />
        </View>

      </Page>
    </Document>
  );
}
