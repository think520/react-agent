const STORAGE_KEY = "bobodan:experience-lesson:v1";

export interface ExperienceProgress {
  answer: string;
  completed: boolean;
}

const EMPTY_PROGRESS: ExperienceProgress = { answer: "", completed: false };

export function readExperienceProgress(): ExperienceProgress {
  try {
    const value = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null") as Partial<ExperienceProgress> | null;
    if (!value || typeof value.answer !== "string" || typeof value.completed !== "boolean") return EMPTY_PROGRESS;
    return { answer: value.answer, completed: value.completed };
  } catch {
    return EMPTY_PROGRESS;
  }
}

export function writeExperienceProgress(progress: ExperienceProgress): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
  } catch {
    // The sample remains usable when local storage is disabled.
  }
}
