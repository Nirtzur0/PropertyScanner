import fs from "node:fs";
import path from "node:path";
import { PlaywrightCrawler } from "crawlee";

type CrawlPlan = {
  job_id: string;
  source_id: string;
  mode: "search" | "listing" | "backfill";
  start_urls: string[];
  max_pages: number;
  max_listings: number;
  page_size: number;
  proxy_policy: Record<string, unknown>;
  session_policy: Record<string, unknown>;
  snapshot_dir: string;
  result_path: string;
};

function parseArgs(argv: string[]): { planPath: string } {
  const planIndex = argv.indexOf("--plan");
  if (planIndex === -1 || planIndex + 1 >= argv.length) {
    throw new Error("missing --plan");
  }
  return { planPath: argv[planIndex + 1] };
}

function appendResult(resultPath: string, payload: Record<string, unknown>): void {
  fs.mkdirSync(path.dirname(resultPath), { recursive: true });
  fs.appendFileSync(resultPath, `${JSON.stringify(payload)}\n`, "utf8");
}

function snapshotPath(snapshotDir: string, requestId: string): string {
  return path.join(snapshotDir, `${requestId}.html`);
}

async function main(): Promise<void> {
  const { planPath } = parseArgs(process.argv.slice(2));
  const plan = JSON.parse(fs.readFileSync(planPath, "utf8")) as CrawlPlan;
  fs.mkdirSync(plan.snapshot_dir, { recursive: true });
  fs.writeFileSync(plan.result_path, "", "utf8");

  const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: Math.max(1, plan.max_pages || plan.max_listings || plan.start_urls.length),
    requestHandlerTimeoutSecs: 90,
    headless: true,
    requestHandler: async ({ request, page, response, log }) => {
      const html = await page.content();
      const requestId = String(request.id ?? Date.now());
      const outPath = snapshotPath(plan.snapshot_dir, requestId);
      fs.writeFileSync(outPath, html, "utf8");
      const blockedSignal =
        response?.status() === 403 ||
        response?.status() === 429 ||
        html.toLowerCase().includes("access denied") ||
        html.toLowerCase().includes("captcha");
      appendResult(plan.result_path, {
        source_id: plan.source_id,
        url: request.loadedUrl ?? request.url,
        status: blockedSignal ? "blocked" : "ok",
        http_status: response?.status() ?? null,
        blocked_signal: blockedSignal,
        snapshot_path: outPath,
        content_type: response?.headers()["content-type"] ?? "text/html",
        fetched_at: new Date().toISOString(),
        error: null,
      });
      log.info(`fetched ${request.url}`);
    },
    failedRequestHandler: async ({ request, error }) => {
      appendResult(plan.result_path, {
        source_id: plan.source_id,
        url: request.loadedUrl ?? request.url,
        status: "failed",
        http_status: null,
        blocked_signal: false,
        snapshot_path: null,
        content_type: null,
        fetched_at: new Date().toISOString(),
        error: String(error),
      });
    },
  });

  await crawler.run(plan.start_urls);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
