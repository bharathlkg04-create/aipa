-- Keep the Render free instance awake: Supabase pg_cron pings the app
-- every 10 minutes (Render sleeps after 15 idle minutes). The query
-- itself also counts as DB activity, so the Supabase free project
-- never auto-pauses either.
--
-- NOTE: only the main app is pinged. Render's free tier shares 750
-- instance-hours/month across ALL free services — one service running
-- 24/7 uses ~744h, so keeping a second one (e.g. the WAHA bridge)
-- awake too would blow the quota mid-month.

create extension if not exists pg_cron;
create extension if not exists pg_net;

select cron.schedule(
  'keep-aipa-awake',
  '*/10 * * * *',
  $$ select net.http_get('https://aipa-03uu.onrender.com/health/live') $$
);
