"use client";

import { Document, Page, Text, View, StyleSheet, Font } from "@react-pdf/renderer";

const styles = StyleSheet.create({
  page: {
    paddingTop: 60, paddingBottom: 60,
    paddingHorizontal: 70,
    fontFamily: "Helvetica",
    fontSize: 11,
    lineHeight: 1.6,
    color: "#1a1a1a",
  },
  header: {
    marginBottom: 24,
    borderBottomWidth: 1,
    borderBottomColor: "#2563eb",
    paddingBottom: 10,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-end",
  },
  brand: { fontSize: 16, fontFamily: "Helvetica-Bold", color: "#2563eb" },
  headerSub: { fontSize: 9, color: "#64748b" },
  title: { fontSize: 13, fontFamily: "Helvetica-Bold", textAlign: "center", marginBottom: 20 },
  body: { fontSize: 11, lineHeight: 1.7 },
  paragraph: { marginBottom: 10 },
  footer: {
    position: "absolute",
    bottom: 24,
    left: 70,
    right: 70,
    borderTopWidth: 0.5,
    borderTopColor: "#e2e8f0",
    paddingTop: 6,
    flexDirection: "row",
    justifyContent: "space-between",
  },
  footerText: { fontSize: 8, color: "#94a3b8" },
  disclaimer: { fontSize: 7.5, color: "#94a3b8", marginTop: 4 },
});

interface Props {
  text:  string;
  title: string;
}

export default function DraftDocument({ text, title }: Props) {
  const today = new Date().toLocaleDateString("pl-PL", { day: "2-digit", month: "long", year: "numeric" });

  // Split text into paragraphs for better rendering
  const paragraphs = text.split(/\n{2,}/).filter(Boolean);

  return (
    <Document title={title} author="LexCorpus" creator="LexCorpus AI">
      <Page size="A4" style={styles.page}>
        {/* Header */}
        <View style={styles.header} fixed>
          <Text style={styles.brand}>LexCorpus</Text>
          <Text style={styles.headerSub}>Dokument wygenerowany {today}</Text>
        </View>

        {/* Title */}
        <Text style={styles.title}>{title.toUpperCase()}</Text>

        {/* Body */}
        <View style={styles.body}>
          {paragraphs.map((para, i) => (
            <Text key={i} style={styles.paragraph}>
              {para.replace(/\n/g, " ")}
            </Text>
          ))}
        </View>

        {/* Footer */}
        <View style={styles.footer} fixed>
          <Text style={styles.footerText}>LexCorpus · lexcorpus.pl</Text>
          <Text style={styles.footerText} render={({ pageNumber, totalPages }) => `${pageNumber} / ${totalPages}`} />
        </View>
        <Text style={styles.disclaimer} fixed>
          Dokument wygenerowany przez AI. Skonsultuj z prawnikiem przed podpisaniem.
        </Text>
      </Page>
    </Document>
  );
}
