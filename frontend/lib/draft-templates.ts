export interface DraftField {
  key:         string;
  label:       string;
  placeholder: string;
  type:        "text" | "textarea" | "date" | "select";
  options?:    string[];
  required:    boolean;
}

export interface DraftTemplate {
  id:          string;
  label:       string;
  description: string;
  icon:        string;
  tier:        "free" | "pro";   // free = dostępne dla wszystkich, pro = wymaga Pro+
  fields:      DraftField[];
  systemHint:  string;           // dodatkowa wskazówka dla LLM
}

export const DRAFT_TEMPLATES: DraftTemplate[] = [
  {
    id:          "wypowiedzenie_pracy",
    label:       "Wypowiedzenie umowy o pracę",
    description: "Wypowiedzenie składane przez pracownika lub pracodawcę",
    icon:        "📄",
    tier:        "free",
    fields: [
      { key: "strona",         label: "Kto składa wypowiedzenie",  placeholder: "pracownik / pracodawca", type: "select", options: ["pracownik", "pracodawca"], required: true },
      { key: "imie_nazwisko",  label: "Imię i nazwisko pracownika", placeholder: "Jan Kowalski",          type: "text",   required: true },
      { key: "pracodawca",     label: "Nazwa pracodawcy",           placeholder: "Firma Sp. z o.o.",       type: "text",   required: true },
      { key: "stanowisko",     label: "Stanowisko",                 placeholder: "Programista",            type: "text",   required: true },
      { key: "data_zatrudnienia", label: "Data zatrudnienia",       placeholder: "2020-01-01",             type: "date",   required: true },
      { key: "okres_wypowiedzenia", label: "Okres wypowiedzenia",   placeholder: "1 miesiąc",              type: "select", options: ["2 tygodnie", "1 miesiąc", "3 miesiące"], required: true },
      { key: "powod",          label: "Powód (opcjonalnie)",        placeholder: "Zmiana miejsca zamieszkania…", type: "textarea", required: false },
    ],
    systemHint: "Uwzględnij przepisy Kodeksu pracy (art. 30-43 KP). Podaj pouczenie o terminie odwołania do sądu pracy.",
  },
  {
    id:          "wezwanie_do_zaplaty",
    label:       "Wezwanie do zapłaty",
    description: "Przedsądowe wezwanie dłużnika do uregulowania należności",
    icon:        "💰",
    tier:        "free",
    fields: [
      { key: "wierzyciel",     label: "Wierzyciel (imię/firma)",   placeholder: "Jan Kowalski / ABC Sp. z o.o.", type: "text", required: true },
      { key: "dluznik",        label: "Dłużnik (imię/firma)",      placeholder: "Piotr Nowak / XYZ Sp. z o.o.", type: "text", required: true },
      { key: "kwota",          label: "Kwota zadłużenia (PLN)",    placeholder: "5 000",                        type: "text", required: true },
      { key: "podstawa",       label: "Podstawa zobowiązania",     placeholder: "faktura VAT nr 12/2024 z dnia 01.03.2024", type: "textarea", required: true },
      { key: "termin",         label: "Termin płatności",          placeholder: "7 dni od otrzymania wezwania", type: "text", required: true },
      { key: "konto",          label: "Numer konta bankowego",     placeholder: "PL61 1090 1014 0000 0712 1981 2874", type: "text", required: false },
    ],
    systemHint: "Powołaj się na art. 455 KC. Zawrzyj informację o konsekwencjach braku zapłaty (odsetki ustawowe za opóźnienie, art. 481 KC, skierowanie sprawy na drogę sądową).",
  },
  {
    id:          "umowa_zlecenie",
    label:       "Umowa zlecenia",
    description: "Umowa cywilnoprawna o wykonanie określonych czynności",
    icon:        "🤝",
    tier:        "pro",
    fields: [
      { key: "zleceniodawca",  label: "Zleceniodawca",             placeholder: "Firma ABC Sp. z o.o., NIP: 123-456-78-90", type: "text",     required: true },
      { key: "zleceniobiorca", label: "Zleceniobiorca",            placeholder: "Jan Kowalski, PESEL: …",                   type: "text",     required: true },
      { key: "przedmiot",      label: "Przedmiot zlecenia",        placeholder: "Prowadzenie szkoleń z zakresu BHP",        type: "textarea", required: true },
      { key: "wynagrodzenie",  label: "Wynagrodzenie",             placeholder: "3 000 zł brutto",                          type: "text",     required: true },
      { key: "termin_od",      label: "Data rozpoczęcia",          placeholder: "",                                         type: "date",     required: true },
      { key: "termin_do",      label: "Data zakończenia",          placeholder: "",                                         type: "date",     required: true },
      { key: "uwagi",          label: "Dodatkowe postanowienia",   placeholder: "np. zakaz konkurencji, prawa autorskie…",  type: "textarea", required: false },
    ],
    systemHint: "Umowa na podstawie art. 734-751 KC. Uwzględnij klauzulę ZUS/NFZ i podatek dochodowy. Dodaj postanowienie o prawie wypowiedzenia (art. 746 KC).",
  },
  {
    id:          "pelnomocnictwo",
    label:       "Pełnomocnictwo",
    description: "Ogólne lub szczególne pełnomocnictwo procesowe lub materialne",
    icon:        "✍️",
    tier:        "pro",
    fields: [
      { key: "mocodawca",      label: "Mocodawca",                 placeholder: "Jan Kowalski, PESEL: …",              type: "text",     required: true },
      { key: "pelnomocnik",    label: "Pełnomocnik",               placeholder: "adw. Anna Nowak, nr wpisu: 1234",     type: "text",     required: true },
      { key: "zakres",         label: "Zakres pełnomocnictwa",     placeholder: "Do reprezentowania przed sądami…",    type: "textarea", required: true },
      { key: "rodzaj",         label: "Rodzaj",                    placeholder: "",                                    type: "select",   options: ["ogólne", "szczególne", "procesowe"], required: true },
      { key: "waznosc",        label: "Ważność",                   placeholder: "bezterminowe / do …",                 type: "text",     required: false },
    ],
    systemHint: "Oparcie na art. 98-109 KC i art. 86-97 KPC. Uwzględnij klauzulę substytucji jeśli wskazana. Pełnomocnictwo procesowe zgodne z wymogami KPC.",
  },
  {
    id:          "nda",
    label:       "Umowa poufności (NDA)",
    description: "Non-disclosure agreement — ochrona informacji poufnych",
    icon:        "🔒",
    tier:        "pro",
    fields: [
      { key: "strona1",        label: "Strona ujawniająca",        placeholder: "ABC Sp. z o.o., NIP: …",              type: "text",     required: true },
      { key: "strona2",        label: "Strona przyjmująca",        placeholder: "XYZ S.A., NIP: …",                   type: "text",     required: true },
      { key: "cel",            label: "Cel ujawnienia",            placeholder: "negocjacje dotyczące współpracy…",    type: "textarea", required: true },
      { key: "okres",          label: "Okres obowiązywania",       placeholder: "2 lata od podpisania",               type: "text",     required: true },
      { key: "kara",           label: "Kara umowna (PLN)",         placeholder: "50 000",                             type: "text",     required: false },
      { key: "prawo_wlasciwe", label: "Prawo właściwe",           placeholder: "prawo polskie",                       type: "text",     required: false },
    ],
    systemHint: "Zdefiniuj precyzyjnie pojęcie informacji poufnych. Uwzględnij wyjątki (informacje publiczne, obowiązek prawny). Powołaj się na przepisy USTAWY o zwalczaniu nieuczciwej konkurencji oraz KC.",
  },
  {
    id:          "umowa_o_dzielo",
    label:       "Umowa o dzieło",
    description: "Umowa rezultatu — wykonanie konkretnego dzieła",
    icon:        "🎨",
    tier:        "pro",
    fields: [
      { key: "zamawiajacy",    label: "Zamawiający",               placeholder: "ABC Sp. z o.o., NIP: …",              type: "text",     required: true },
      { key: "wykonawca",      label: "Wykonawca",                 placeholder: "Jan Kowalski, PESEL: …",              type: "text",     required: true },
      { key: "dzielo",         label: "Opis dzieła",               placeholder: "Projekt graficzny strony internetowej…", type: "textarea", required: true },
      { key: "wynagrodzenie",  label: "Wynagrodzenie",             placeholder: "5 000 zł brutto",                     type: "text",     required: true },
      { key: "termin",         label: "Termin wykonania",          placeholder: "",                                    type: "date",     required: true },
      { key: "prawa_autorskie", label: "Prawa autorskie",          placeholder: "przeniesienie autorskich praw majątkowych / licencja", type: "select", options: ["przeniesienie praw majątkowych", "licencja wyłączna", "licencja niewyłączna"], required: true },
    ],
    systemHint: "Umowa na podstawie art. 627-646 KC. Uwzględnij przepisy Prawa autorskiego (ustawa z 4.02.1994) jeśli dzieło ma charakter twórczy. Dodaj postanowienie o odbiorze dzieła i wadach.",
  },
];
