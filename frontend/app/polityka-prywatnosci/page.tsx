import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Polityka Prywatności — LexCorpus",
  description: "Polityka prywatności LexCorpus — informacje o przetwarzaniu danych osobowych zgodnie z RODO.",
};

const EFFECTIVE_DATE = "1 czerwca 2026 r.";
const CONTACT_EMAIL  = "kontakt@lexcorpus.pl";
const BASE_URL       = "https://lexcorpus.pl";

export default function PolitykaPrywatnosci() {
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center gap-3">
          <Link href="/" className="text-xl font-bold">
            <span className="text-blue-600">Lex</span><span className="text-slate-900 dark:text-white">Corpus</span>
          </Link>
          <span className="text-slate-300 dark:text-slate-600">·</span>
          <h1 className="text-base font-medium text-slate-600 dark:text-slate-400">Polityka Prywatności</h1>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-12 prose prose-slate dark:prose-invert prose-headings:font-bold prose-a:text-blue-600">
        <p className="text-sm text-slate-500 dark:text-slate-400 not-prose mb-8">
          Wersja: {EFFECTIVE_DATE}
        </p>

        <h2>1. Administrator danych</h2>
        <p>
          Administratorem Twoich danych osobowych jest operator platformy LexCorpus dostępnej pod adresem{" "}
          <strong>{BASE_URL}</strong>. Kontakt: <strong>{CONTACT_EMAIL}</strong>
        </p>

        <h2>2. Podstawa prawna i cel przetwarzania</h2>
        <p>Przetwarzamy Twoje dane w oparciu o:</p>
        <ul>
          <li>
            <strong>Art. 6 ust. 1 lit. b RODO</strong> — wykonanie umowy (świadczenie usługi dostępu do Serwisu,
            obsługa konta, rozliczenia płatności).
          </li>
          <li>
            <strong>Art. 6 ust. 1 lit. a RODO</strong> — zgoda (newsletter, powiadomienia o zmianach w prawie).
          </li>
          <li>
            <strong>Art. 6 ust. 1 lit. f RODO</strong> — prawnie uzasadniony interes (bezpieczeństwo, zapobieganie
            nadużyciom, statystyki użytkowania).
          </li>
          <li>
            <strong>Art. 6 ust. 1 lit. c RODO</strong> — obowiązek prawny (wystawianie faktur VAT).
          </li>
        </ul>

        <h2>3. Zakres przetwarzanych danych</h2>
        <ul>
          <li><strong>Dane konta:</strong> adres e-mail, data rejestracji, plan subskrypcji.</li>
          <li><strong>Dane użytkowania:</strong> historia zapytań, feedback (kciuk góra/dół), dzienne liczniki zapytań.</li>
          <li><strong>Dane płatności:</strong> ID klienta Stripe, ID subskrypcji, ID planu — bez numeru karty płatniczej.</li>
          <li><strong>Dane techniczne:</strong> adres IP, nagłówki HTTP, logi dostępowe (przechowywane max. 30 dni).</li>
        </ul>

        <h2>4. Odbiorcy danych</h2>
        <p>Twoje dane mogą być przekazywane:</p>
        <ul>
          <li><strong>Stripe, Inc.</strong> (USA) — obsługa płatności; Standard Contractual Clauses + DPA.</li>
          <li><strong>Dostawca hostingu VPS</strong> — przechowywanie danych na serwerach w UE.</li>
          <li><strong>OpenAI, Inc.</strong> (USA) — przetwarzanie treści zapytań w celu generowania odpowiedzi;
            zapytania mogą zawierać fragmenty tekstu wprowadzonego przez Użytkownika.</li>
        </ul>
        <p>
          Nie sprzedajemy danych osobowych podmiotom trzecim w celach marketingowych.
        </p>

        <h2>5. Okres przechowywania</h2>
        <ul>
          <li>Dane konta — do momentu usunięcia konta lub przez 3 lata od ostatniego logowania.</li>
          <li>Historia zapytań — 12 miesięcy (możesz ją usunąć w dowolnym momencie w <em>/history</em>).</li>
          <li>Dane fakturowe — 5 lat (obowiązek podatkowy).</li>
          <li>Logi techniczne — 30 dni.</li>
        </ul>

        <h2>6. Twoje prawa</h2>
        <p>Na podstawie RODO przysługuje Ci:</p>
        <ul>
          <li>Prawo dostępu do danych (art. 15 RODO).</li>
          <li>Prawo do sprostowania danych (art. 16 RODO).</li>
          <li>Prawo do usunięcia danych (<em>"prawo do bycia zapomnianym"</em>) (art. 17 RODO).</li>
          <li>Prawo do ograniczenia przetwarzania (art. 18 RODO).</li>
          <li>Prawo do przenoszenia danych (art. 20 RODO).</li>
          <li>Prawo do sprzeciwu (art. 21 RODO).</li>
          <li>Prawo do wycofania zgody (nie wpływa na legalność przetwarzania przed wycofaniem).</li>
        </ul>
        <p>
          Wnioski kieruj na: <strong>{CONTACT_EMAIL}</strong>. Odpowiedź nastąpi w ciągu 30 dni.
          Przysługuje Ci także prawo skargi do <strong>Prezesa Urzędu Ochrony Danych Osobowych</strong>{" "}
          (<a href="https://uodo.gov.pl" target="_blank" rel="noopener noreferrer">uodo.gov.pl</a>).
        </p>

        <h2>7. Pliki cookie</h2>
        <p>
          Serwis korzysta wyłącznie z cookies niezbędnych do działania sesji (<code>next-auth.session-token</code>).
          Nie stosujemy cookies śledzących ani reklamowych.
        </p>

        <h2>8. Bezpieczeństwo</h2>
        <p>
          Dane przechowywane są na zaszyfrowanych serwerach w Unii Europejskiej.
          Połączenie z Serwisem jest zabezpieczone protokołem TLS 1.2+.
          Hasła nie są przechowywane — stosujemy logowanie bez hasła (magic link).
        </p>

        <h2>9. Zmiany polityki</h2>
        <p>
          O istotnych zmianach Polityki Prywatności poinformujemy e-mailem z 14-dniowym wyprzedzeniem.
        </p>

        <h2>10. Kontakt</h2>
        <p>
          W sprawach dotyczących ochrony danych osobowych: <strong>{CONTACT_EMAIL}</strong>
        </p>
      </main>

      <footer className="border-t border-slate-200 dark:border-slate-700 py-8 text-center text-sm text-slate-400">
        <Link href="/" className="hover:text-blue-600 transition-colors">← Powrót do LexCorpus</Link>
        <span className="mx-3">·</span>
        <Link href="/regulamin" className="hover:text-blue-600 transition-colors">Regulamin</Link>
      </footer>
    </div>
  );
}
