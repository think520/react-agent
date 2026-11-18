import { beforeEach, describe, expect, it } from "vitest";

import { readExperienceProgress, writeExperienceProgress } from "./experienceLesson";

beforeEach(() => window.localStorage.clear());

describe("sample lesson progress", () => {
  it("persists an unfinished answer without creating a learning record", () => {
    writeExperienceProgress({ answer: "B", completed: false });

    expect(readExperienceProgress()).toEqual({ answer: "B", completed: false });
    expect(window.localStorage.length).toBe(1);
    expect(window.localStorage.key(0)).toBe("bobodan:experience-lesson:v1");
  });

  it("ignores invalid saved progress", () => {
    window.localStorage.setItem("bobodan:experience-lesson:v1", "not-json");
    expect(readExperienceProgress()).toEqual({ answer: "", completed: false });
  });
});
