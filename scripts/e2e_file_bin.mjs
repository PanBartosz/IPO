import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.env.E2E_BASE_URL || "http://localhost:5000";
const adminUser = process.env.E2E_ADMIN_USER || "admin";
const adminPassword = process.env.E2E_ADMIN_PASSWORD || "dev-password";
const seedPath = process.env.E2E_FILE_BIN_SEED || "output/e2e_file_bin.json";
const screenshotPath = process.env.E2E_SCREENSHOT || "output/playwright/file-bin-e2e.png";
const uploadDir = process.env.E2E_UPLOAD_DIR || "output/playwright";

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
await fs.mkdir(uploadDir, { recursive: true });

const uploadPath = path.join(uploadDir, payload.filename);
await fs.writeFile(uploadPath, payload.content, "utf8");

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  acceptDownloads: true,
  viewport: { width: 1440, height: 1000 },
});
const page = await context.newPage();

try {
  await page.goto(`${baseUrl}/file-bin`, { waitUntil: "networkidle" });
  await assertVisible(page.getByRole("heading", { name: "Emergency File Bin" }), "File Bin heading");
  await page.fill('input[name="access_code"]', payload.code);
  await page.fill('input[name="staff_name"]', payload.staff_name);
  await page.fill('input[name="room"]', payload.room);
  await page.fill('input[name="student_identifier"]', payload.student_identifier);
  await page.fill('textarea[name="note"]', payload.note);
  await page.setInputFiles('input[name="file"]', uploadPath);
  await submitAndWait(page, 'input[type="submit"]');
  assert.ok(
    await page.getByText(/File received\. Reference: File Bin #/).first().isVisible(),
    "File Bin success toast missing",
  );

  await page.goto(`${baseUrl}/admin/login`, { waitUntil: "networkidle" });
  await page.fill('input[name="username"]', adminUser);
  await page.fill('input[name="password"]', adminPassword);
  await submitAndWait(page, 'input[type="submit"]');
  assert.ok(page.url().includes("/admin"), "Admin login did not reach an admin page");

  await page.goto(`${baseUrl}/admin/file-bin`, { waitUntil: "networkidle" });
  const row = page.locator("tr", { hasText: payload.student_identifier }).first();
  await assertVisible(row, "uploaded File Bin row");
  assert.ok(await row.getByText(payload.filename).first().isVisible(), "uploaded filename is missing");
  assert.ok(await row.getByText("Unreviewed").first().isVisible(), "unreviewed status is missing");

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    row.getByText(payload.filename).first().click(),
  ]);
  const downloadedPath = await download.path();
  assert.ok(downloadedPath, "download path was not available");
  const downloaded = await fs.readFile(downloadedPath, "utf8");
  assert.equal(downloaded, payload.content, "downloaded File Bin content changed");

  await row.locator('textarea[name="admin_note"]').fill("E2E reviewed");
  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle" }),
    row.getByRole("button", { name: "Mark reviewed" }).click(),
  ]);
  await page.goto(`${baseUrl}/admin/file-bin`, { waitUntil: "networkidle" });
  const reviewedRow = page.locator("tr", { hasText: payload.student_identifier }).first();
  await assertVisible(reviewedRow, "reviewed File Bin row");
  assert.ok(await reviewedRow.getByText("Reviewed").first().isVisible(), "reviewed status is missing");
  assert.ok(await reviewedRow.getByText("E2E reviewed").first().isVisible(), "admin note is missing");

  await page.screenshot({ path: screenshotPath, fullPage: true });
  console.log(`File Bin e2e passed. Screenshot: ${screenshotPath}`);
} finally {
  await context.close();
  await browser.close();
}
