import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anon = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const supabaseConfigured = Boolean(url && anon);

// A missing config still lets the app render a helpful setup message instead of crashing.
export const supabase = createClient(url ?? "https://placeholder.supabase.co", anon ?? "placeholder");

export const ADMIN_EMAIL = (import.meta.env.VITE_ADMIN_EMAIL as string | undefined) ?? "";
