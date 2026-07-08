// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { describe, it, expect } from "vitest";
import * as fc from "fast-check";

describe("Test setup verification", () => {
  it("vitest is working", () => {
    expect(true).toBe(true);
  });

  it("fast-check is working", () => {
    fc.assert(
      fc.property(fc.integer(), (n) => {
        return n + 0 === n;
      }),
      { numRuns: 100 },
    );
  });
});
