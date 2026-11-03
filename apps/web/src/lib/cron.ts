// One-click schedules for the cron builder.
export const CRON_PRESETS = [
  { label: "Every hour", cron: "0 * * * *" },
  { label: "Every 2 hours", cron: "0 */2 * * *" },
  { label: "Weekday mornings", cron: "0 9 * * 1-5" },
  { label: "Twice a day", cron: "0 9,15 * * *" },
  { label: "Daily at 7", cron: "0 7 * * *" },
  { label: "Mondays", cron: "0 8 * * 1" },
];
