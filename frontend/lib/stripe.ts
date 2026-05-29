import Stripe from "stripe";

// Inicjowany tylko server-side (sekret nie trafia do przeglądarki)
export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY ?? "");

// Plany muszą być wcześniej utworzone w dashboardzie Stripe.
// Ustaw STRIPE_PRICE_PRO i STRIPE_PRICE_KANCELARIA w .env
export const STRIPE_PRICES: Record<string, string> = {
  pro:        process.env.STRIPE_PRICE_PRO        ?? "",
  kancelaria: process.env.STRIPE_PRICE_KANCELARIA ?? "",
};

export const PLAN_META = {
  pro: {
    name:        "Pro",
    price:       "49 zł / mies.",
    description: "500 zapytań dziennie, priorytetowe wyniki, eksport PDF",
    color:       "blue",
  },
  kancelaria: {
    name:        "Kancelaria",
    price:       "299 zł / mies.",
    description: "Nieograniczone zapytania, dostęp API, 5 użytkowników, SLA",
    color:       "purple",
  },
} as const;
