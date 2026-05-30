import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Regulamin — LexCorpus",
  description: "Regulamin świadczenia usług LexCorpus — polskiego asystenta prawnego opartego na AI.",
};

const EFFECTIVE_DATE = "1 czerwca 2026 r.";
const CONTACT_EMAIL  = "kontakt@lexcorpus.pl";
const BASE_URL       = "https://lexcorpus.pl";

export default function RegulaminPage() {
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center gap-3">
          <Link href="/" className="text-xl font-bold">
            <span className="text-blue-600">Lex</span><span className="text-slate-900 dark:text-white">Corpus</span>
          </Link>
          <span className="text-slate-300 dark:text-slate-600">·</span>
          <h1 className="text-base font-medium text-slate-600 dark:text-slate-400">Regulamin</h1>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-12 prose prose-slate dark:prose-invert prose-headings:font-bold prose-a:text-blue-600">
        <p className="text-sm text-slate-500 dark:text-slate-400 not-prose mb-8">
          Wersja: {EFFECTIVE_DATE}
        </p>

        <h2>§ 1. Definicje</h2>
        <p>
          1. <strong>Usługodawca</strong> — operator platformy LexCorpus dostępnej pod adresem <strong>{BASE_URL}</strong>.<br />
          2. <strong>Użytkownik</strong> — osoba fizyczna, osoba prawna lub jednostka organizacyjna nieposiadająca osobowości prawnej,
          która korzysta z Serwisu.<br />
          3. <strong>Serwis</strong> — aplikacja internetowa LexCorpus wraz z API i powiązanymi usługami.<br />
          4. <strong>Usługa</strong> — dostęp do systemu wspomagającego analizę polskich aktów prawnych i orzecznictwa przy użyciu
          sztucznej inteligencji.
        </p>

        <h2>§ 2. Zakres usługi</h2>
        <p>
          1. LexCorpus świadczy usługę dostępu do asystenta prawnego opartego na technologii RAG (<em>Retrieval-Augmented Generation</em>),
          który przeszukuje bazę ponad 636 000 polskich dokumentów prawnych (ISAP, SAOS, EUR-Lex, KIS) i generuje odpowiedzi
          przy użyciu modelu językowego.<br />
          2. Serwis <strong>nie świadczy usług prawniczych</strong> w rozumieniu ustawy z dnia 6 lipca 1982 r. o radcach prawnych
          ani ustawy z dnia 26 maja 1982 r. — Prawo o adwokaturze. Odpowiedzi generowane przez system mają charakter
          informacyjny i edukacyjny.<br />
          3. Użytkownik jest zobowiązany do samodzielnej weryfikacji informacji uzyskanych za pośrednictwem Serwisu
          przed podjęciem jakichkolwiek decyzji prawnych lub finansowych.
        </p>

        <h2>§ 3. Rejestracja i konto</h2>
        <p>
          1. Korzystanie z Serwisu wymaga założenia konta przy użyciu adresu e-mail (logowanie bez hasła — <em>magic link</em>).<br />
          2. Użytkownik zobowiązuje się do podania prawdziwego adresu e-mail oraz aktualizacji danych w razie ich zmiany.<br />
          3. Konto jest niezbywalne i nie może być udostępniane osobom trzecim bez pisemnej zgody Usługodawcy.<br />
          4. Jeden adres e-mail może być powiązany wyłącznie z jednym kontem.
        </p>

        <h2>§ 4. Plany i płatności</h2>
        <p>
          1. Serwis oferuje trzy plany: <strong>Free</strong> (bezpłatny), <strong>Pro</strong> (płatny) oraz
          <strong>Kancelaria</strong> (płatny). Aktualne ceny i limity podane są na stronie <em>/upgrade</em>.<br />
          2. Płatności obsługiwane są przez zewnętrznego operatora płatności <strong>Stripe, Inc.</strong>
          Usługodawca nie przechowuje danych kart płatniczych.<br />
          3. Subskrypcja jest naliczana z góry za każdy miesiąc. Użytkownik może anulować subskrypcję w dowolnym momencie;
          dostęp do planu płatnego trwa do końca opłaconego okresu.<br />
          4. Faktury VAT dostępne są w portalu klienta Stripe.
        </p>

        <h2>§ 5. Dozwolone użycie</h2>
        <p>
          Zabrania się:<br />
          a) automatycznego pobierania treści Serwisu (scraping) bez pisemnej zgody Usługodawcy,<br />
          b) odsprzedaży dostępu do Serwisu,<br />
          c) korzystania z Serwisu w sposób naruszający przepisy prawa,<br />
          d) działań zmierzających do obejścia limitów zapytań lub zabezpieczeń technicznych,<br />
          e) publikowania wyników generowanych przez AI jako porady prawnej bez oznaczenia ich źródła i statusu.
        </p>

        <h2>§ 6. Ograniczenie odpowiedzialności</h2>
        <p>
          1. Usługodawca nie ponosi odpowiedzialności za decyzje podjęte przez Użytkownika na podstawie treści
          wygenerowanych przez system AI.<br />
          2. Dokładność i kompletność danych zależy od zasobów zewnętrznych (ISAP, SAOS, EUR-Lex, KIS).
          Usługodawca nie gwarantuje aktualności wszystkich dokumentów.<br />
          3. Łączna odpowiedzialność Usługodawcy wobec Użytkownika nie przekracza kwoty uiszczonej przez Użytkownika
          w ciągu ostatnich 12 miesięcy lub 100 PLN (w zależności od tego, która kwota jest wyższa).
        </p>

        <h2>§ 7. Prywatność</h2>
        <p>
          Zasady przetwarzania danych osobowych określa{" "}
          <Link href="/polityka-prywatnosci">Polityka Prywatności</Link>.
        </p>

        <h2>§ 8. Zmiany regulaminu</h2>
        <p>
          Usługodawca zastrzega prawo do zmiany Regulaminu z 14-dniowym wyprzedzeniem. O zmianie Użytkownicy
          zostaną powiadomieni e-mailem na adres przypisany do konta.
        </p>

        <h2>§ 9. Rozwiązanie umowy</h2>
        <p>
          1. Użytkownik może usunąć konto w dowolnym momencie w ustawieniach (<em>/account/settings</em>).<br />
          2. Usługodawca może zawiesić lub usunąć konto w przypadku rażącego naruszenia Regulaminu.
        </p>

        <h2>§ 10. Kontakt i prawo właściwe</h2>
        <p>
          W sprawach związanych z Regulaminem prosimy o kontakt: <strong>{CONTACT_EMAIL}</strong>.<br />
          Regulamin podlega prawu polskiemu. Wszelkie spory rozstrzygane będą przez sąd właściwy dla siedziby Usługodawcy.
        </p>
      </main>

      <footer className="border-t border-slate-200 dark:border-slate-700 py-8 text-center text-sm text-slate-400">
        <Link href="/" className="hover:text-blue-600 transition-colors">← Powrót do LexCorpus</Link>
        <span className="mx-3">·</span>
        <Link href="/polityka-prywatnosci" className="hover:text-blue-600 transition-colors">Polityka prywatności</Link>
      </footer>
    </div>
  );
}
