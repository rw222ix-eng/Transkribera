import { test, expect, failOnConsoleError } from "../helpers/app";

// Segmented / toggle controls must expose their selection to assistive tech via
// aria-pressed (until this fix only the chat "Tänk djupare" toggle did). This
// samples a "select-one" control (nav tabs) and a "multi-toggle" control (format
// chips); the fix applies the same attribute uniformly to the sibling segmented
// controls (language, resultatspråk, subtitle/embed, post-process op, search mode).
test("segmented controls expose aria-pressed reflecting selection", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await page.goto("/");

  // Nav tabs: exactly the active tab is pressed; it tracks navigation.
  const navT = page.getByRole("button", { name: "Transkribera", exact: true });
  const navH = page.getByRole("button", { name: "Inspelningar", exact: true });
  await expect(navT).toHaveAttribute("aria-pressed", "true");
  await expect(navH).toHaveAttribute("aria-pressed", "false");
  await navH.click();
  await expect(navH).toHaveAttribute("aria-pressed", "true");
  await expect(navT).toHaveAttribute("aria-pressed", "false");

  // Add a sample file to reach the settings step where the format chips live.
  await navT.click();
  await page.getByRole("button", { name: "Prova ett exempel" }).click();

  // Format chips are independent toggles: SRT/TXT on by default, VTT off.
  const srt = page.getByRole("button", { name: "SRT", exact: true });
  const vtt = page.getByRole("button", { name: "VTT", exact: true });
  await expect(srt).toHaveAttribute("aria-pressed", "true");
  await expect(vtt).toHaveAttribute("aria-pressed", "false");
  await vtt.click();
  await expect(vtt).toHaveAttribute("aria-pressed", "true");

  expect(errors, errors.join("\n")).toEqual([]);
});
