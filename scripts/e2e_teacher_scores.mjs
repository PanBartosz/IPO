import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.env.E2E_BASE_URL || "http://localhost:5000";
const adminUser = process.env.E2E_ADMIN_USER || "admin";
const adminPassword = process.env.E2E_ADMIN_PASSWORD || "dev-password";
const seedPath = process.env.E2E_TEACHER_SCORES_SEED || "output/e2e_teacher_scores.json";
const screenshotPath = process.env.E2E_SCREENSHOT || "output/playwright/teacher-scores-e2e.png";

async function inputValue(page, selector) {
  const locator = page.locator(selector);
  await assertVisible(locator, selector);
  return locator.inputValue();
}

async function assertVisible(locator, label) {
  const count = await locator.count();
  assert.ok(count > 0, `${label} was not found`);
  assert.ok(await locator.first().isVisible(), `${label} is not visible`);
}

async function submitAndWait(page, buttonSelector) {
  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle" }),
    page.locator(buttonSelector).click(),
  ]);
}

const payload = JSON.parse(await fs.readFile(seedPath, "utf8"));
await fs.mkdir(path.dirname(screenshotPath), { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

try {
  await page.goto(`${baseUrl}/admin/login`, { waitUntil: "networkidle" });
  await page.fill('input[name="username"]', adminUser);
  await page.fill('input[name="password"]', adminPassword);
  await submitAndWait(page, 'input[type="submit"]');
  assert.ok(page.url().includes("/admin"), "Admin login did not reach an admin page");

  await page.goto(`${baseUrl}/admin/teachers/${payload.teacher_id}/scores`, { waitUntil: "networkidle" });
  await assertVisible(page.getByRole("heading", { name: /Scores/ }).first(), "teacher scores heading");
  assert.ok(await page.getByText(payload.teacher_name).first().isVisible(), "teacher name not visible");

  await page.fill(`#stage_1-scores input[name="score_${payload.stage1_assignment_id}"]`, "8");
  await submitAndWait(page, '#stage_1-scores button[type="submit"]');
  assert.ok(await page.getByText("Stage 1 scores saved.").first().isVisible(), "Stage 1 save toast missing");

  await page.fill(`#stage_2-scores input[name="score_${payload.stage2_assignment_id}"]`, "9");
  await submitAndWait(page, '#stage_2-scores button[type="submit"]');
  assert.ok(await page.getByText("Stage 2 scores saved.").first().isVisible(), "Stage 2 save toast missing");

  await page.goto(`${baseUrl}/admin/uploads/${payload.stage1_student_id}/scores`, { waitUntil: "networkidle" });
  assert.equal(
    await inputValue(page, `select[name="score_${payload.teacher_id}"]`),
    "8",
    "Stage 1 score did not appear on the student-centered page",
  );

  await page.goto(`${baseUrl}/admin/stage2/${payload.stage2_student_id}`, { waitUntil: "networkidle" });
  assert.equal(
    await inputValue(page, `select[name="score_${payload.teacher_id}"]`),
    "9",
    "Stage 2 score did not appear on the student-centered page",
  );

  await page.goto(`${baseUrl}/admin/teachers/${payload.teacher_id}/scores`, { waitUntil: "networkidle" });
  assert.equal(
    await inputValue(page, `#stage_1-scores input[name="score_${payload.stage1_assignment_id}"]`),
    "8",
    "Stage 1 score was not retained on the teacher-centered page",
  );
  assert.equal(
    await inputValue(page, `#stage_2-scores input[name="score_${payload.stage2_assignment_id}"]`),
    "9",
    "Stage 2 score was not retained on the teacher-centered page",
  );
  await page.screenshot({ path: screenshotPath, fullPage: true });
  console.log(`Teacher score e2e passed. Screenshot: ${screenshotPath}`);
} finally {
  await browser.close();
}
