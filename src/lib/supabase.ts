import { createClient } from "@supabase/supabase-js";

const url = ((import.meta.env.VITE_SUPABASE_URL as string | undefined) ?? "").trim();
const anon = ((import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined) ?? "").trim();

export const supabaseConfigured = Boolean(url && anon);

// A missing or empty config still lets the app render a setup message instead of a blank page.
export const supabase = createClient(url || "https://placeholder.supabase.co", anon || "placeholder");

export const ADMIN_EMAIL = ((import.meta.env.VITE_ADMIN_EMAIL as string | undefined) ?? "").trim();
