import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AttributionBadges } from "./common";
import type { Attribution } from "../types";

describe("AttributionBadges", () => {
  it("shows both web and local sources for a mixed attribution", () => {
    const attribution: Attribution = {
      kind: "mixed",
      sources: [
        {
          source_type: "local",
          source_id: "chunk-1",
          title: "Lesson 1",
          document_id: "doc-1",
        },
        {
          source_type: "web",
          source_id: "snapshot-1",
          title: "Guide",
          url: "https://example.com/guide",
        },
      ],
    };

    render(
      <MemoryRouter>
        <AttributionBadges attribution={attribution} />
      </MemoryRouter>,
    );

    expect(screen.getByText(/网页来源 · Guide/)).toBeInTheDocument();
    expect(screen.getByText(/本地资料 · Lesson 1/)).toBeInTheDocument();
  });
});
