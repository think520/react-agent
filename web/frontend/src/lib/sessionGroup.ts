export const SESSION_GROUP_LABELS = ["今天", "昨天", "本周", "更早"] as const;

export type SessionGroupLabel = (typeof SESSION_GROUP_LABELS)[number];

/** Buckets a timestamp into 今天 / 昨天 / 本周 / 更早 relative to `now`. */
export function sessionGroup(value: string, now = new Date()): SessionGroupLabel {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "更早";
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const dayDiff = Math.round((startToday.getTime() - startDate.getTime()) / 86_400_000);
  if (dayDiff === 0) return "今天";
  if (dayDiff === 1) return "昨天";
  const weekday = startToday.getDay() || 7;
  const startWeek = new Date(startToday);
  startWeek.setDate(startToday.getDate() - weekday + 1);
  if (startDate >= startWeek) return "本周";
  return "更早";
}
