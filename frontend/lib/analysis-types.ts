export interface AnalysisDates {
  zawarcia:          string | null;
  obowiazywania_od:  string | null;
  obowiazywania_do:  string | null;
  inne:              string[];
}

export interface KeyProvision {
  tytuł:  string;
  treść:  string;
}

export interface RedFlag {
  powaga:   "wysoka" | "średnia" | "niska";
  opis:     string;
  fragment: string;
}

export type Rekomendacja =
  | "podpisać"
  | "podpisać_po_negocjacjach"
  | "odrzucić"
  | "skonsultować_z_prawnikiem";

export interface DocumentAnalysis {
  typ_dokumentu:         string;
  strony:                string[];
  daty:                  AnalysisDates;
  kluczowe_postanowienia: KeyProvision[];
  zobowiazania: {
    strona_1: string[];
    strona_2: string[];
  };
  czerwone_flagi:  RedFlag[];
  podsumowanie:    string;
  rekomendacja:    Rekomendacja;
}

export const REKOMENDACJA_META: Record<Rekomendacja, { label: string; color: string; bg: string }> = {
  podpisać: {
    label: "Można podpisać",
    color: "text-green-700 dark:text-green-300",
    bg:    "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800",
  },
  podpisać_po_negocjacjach: {
    label: "Podpisać po negocjacjach",
    color: "text-amber-700 dark:text-amber-300",
    bg:    "bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800",
  },
  odrzucić: {
    label: "Odrzucić",
    color: "text-red-700 dark:text-red-300",
    bg:    "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800",
  },
  skonsultować_z_prawnikiem: {
    label: "Skonsultuj z prawnikiem",
    color: "text-blue-700 dark:text-blue-300",
    bg:    "bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800",
  },
};

export const POWAGA_META = {
  wysoka:  { label: "Wysoka",  dot: "bg-red-500",    text: "text-red-700 dark:text-red-300" },
  średnia: { label: "Średnia", dot: "bg-amber-500",  text: "text-amber-700 dark:text-amber-300" },
  niska:   { label: "Niska",   dot: "bg-yellow-400", text: "text-yellow-700 dark:text-yellow-300" },
};
