import { createClient } from "@supabase/supabase-js";
import { CONFIG } from "../config";

const clean = (v: string | undefined) => (v ?? "").trim();
const url = clean(import.meta.env.VITE_SUPABASE_URL) || CONFIG.supabase.url;
const anon = clean(import.meta.env.VITE_SUPABASE_ANON_KEY) || CONFIG.supabase.publishableKey;

export const supabaseConfigured = Boolean(url && anon);

// A missing or empty config still lets the app render a setup message instead of a blank page.
export const supabase = createClient(url || "https://placeholder.supabase.co", anon || "placeholder");

export const ADMIN_EMAIL = clean(import.meta.env.VITE_ADMIN_EMAIL) || CONFIG.supabase.adminEmail;
