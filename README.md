# Match Film

Youth soccer game film archive + best-effort team stats. Video lives on YouTube (unlisted);
this app stores metadata, timestamps, and derived stats in Supabase and runs on Vercel.
Zero recurring cost, one admin password, read-only links for parents.

## Stack
- **Web**: Vite + React + TypeScript, react-router, recharts. `src/`
- **DB**: Supabase Postgres with RLS. `supabase/migrations/0001_schema.sql`
- **Analyzer**: Python CLI, runs on your Mac on demand. `analyzer/`

## Setup (one time)
1. **Supabase** (personal account): create a project, run `supabase/migrations/0001_schema.sql`
   in the SQL editor. In Authentication → Users, add one user (email + password). That is the
   admin. Disable public sign-ups in Authentication → Providers → Email.
2. **Config**: put the project URL, publishable key, and admin email in `src/config.ts`.
   They are public by design (RLS is the security boundary). `.env` can override them.
3. `npm install && npm run dev`
4. **Vercel** (personal account): import the repo. No env vars needed. `vercel.json`
   already rewrites all routes to `index.html`.

## Weekly flow
1. After the game, BallerCam saves the processed 1080p file to the iPhone camera roll.
   Upload it to YouTube as **unlisted**. (The BallerCam live-stream link is for watching live;
   YouTube is the archive.)
2. Admin → `+ Game`. Paste the URL, fill in the date/opponent/score. If you also get the raw
   4K fisheye out of the phone, upload it unlisted too and attach it from Edit → Video sources
   as a *Wide-angle source*; viewers never see it, the analyzer prefers it for pitch geometry.
3. Open the game. **Periods** tab: scrub to kickoff / halftime / 2nd half / full time and press Set.
4. Watch and tag with hotkeys: `g` goal, `x` shot, `c` chance, `s` save, `t` turnover, `k` corner,
   `f` free kick, `i` throw-in, `p` penalty, `n` note. Hold **Shift** for the opponent. Shots and goals
   open the pitch to click a location; xG computes immediately.
5. **Chapters** tab → copy → paste into the YouTube description.
6. **Publish**. Share `/g/<id>` (or a tag's 🔗 link to jump to that moment). `/g/<id>/report` is the report card.

## Config
`src/config.ts` holds club name, colours, and default pitch size. Per-game pitch dimensions
override the default (youth pitches vary), and xG uses whichever applies.

## Analyzer (optional, Phase 2/3)
See `analyzer/README.md`. Queue a run from the game's **Analysis** tab, then run the CLI.
Everything it produces is a proposal shown with ≈ or a dashed outline until a human confirms it.

## Privacy
Unlisted only, `noindex`, no per-player data anywhere (not even tracker IDs), no rosters,
no schedules. Team management stays in Heja.
