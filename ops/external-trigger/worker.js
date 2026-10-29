// External hourly trigger for the Matatiele storm check (R3). NOT ACTIVE until deployed with a token.
//
// Cloudflare Worker with a Cron Trigger only: it has no fetch handler, so it exposes no
// HTTP endpoint. Each hour it asks GitHub to start the existing workflow through the
// workflow_dispatch API. It never sends SMS itself, never chooses recipients and never
// requests the connectivity test; all warning logic stays in the GitHub workflow.
//
// Secret (set with `wrangler secret put GITHUB_DISPATCH_TOKEN`, never in this file):
//   GITHUB_DISPATCH_TOKEN  fine-grained PAT, this repository only, "Actions: read and write".

const API = 'https://api.github.com';
const DEFAULTS = {
  GITHUB_REPOSITORY: 'mdvar2/matatiele-storm-early-warning-system',
  WORKFLOW_FILE: 'scheduled-storm-sms.yml',
  GITHUB_REF: 'main',
};
const ATTEMPT_TIMEOUT_MS = 10000;
const RETRY_DELAY_MS = 5000;

export function slotIso(scheduledTime) {
  // Whole-second UTC, e.g. 2026-10-30T07:05:00Z (the format the workflow input accepts).
  return new Date(Math.floor(scheduledTime / 1000) * 1000).toISOString().replace('.000Z', 'Z');
}

export function dispatchRequest(env, scheduledTime) {
  const repo = env.GITHUB_REPOSITORY || DEFAULTS.GITHUB_REPOSITORY;
  const workflow = env.WORKFLOW_FILE || DEFAULTS.WORKFLOW_FILE;
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo) || !/^[A-Za-z0-9_.-]+\.ya?ml$/.test(workflow)) {
    throw new Error('invalid repository or workflow configuration');
  }
  return {
    url: `${API}/repos/${repo}/actions/workflows/${workflow}/dispatches`,
    body: {
      ref: env.GITHUB_REF || DEFAULTS.GITHUB_REF,
      // Fixed values: the external trigger can only start the normal forecast check.
      inputs: { send_test_sms: 'false', trigger_source: 'external_scheduler', scheduled_for: slotIso(scheduledTime) },
    },
  };
}

async function attempt(fetchImpl, url, token, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ATTEMPT_TIMEOUT_MS);
  try {
    const response = await fetchImpl(url, {
      method: 'POST',
      signal: controller.signal,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'Content-Type': 'application/json',
        'User-Agent': 'matatiele-external-trigger',
      },
      body: JSON.stringify(body),
    });
    return { status: response.status };
  } catch (error) {
    return { status: 0, error: error && error.name === 'AbortError' ? 'timeout' : 'network_error' };
  } finally {
    clearTimeout(timer);
  }
}

// Returns an outcome code. Never logs or returns the token or response bodies.
// Retries once only for network errors and 5xx: a duplicated dispatch is harmless because the
// workflow's concurrency group and the per-hour ledger lock prevent a second SMS.
export async function dispatch(env, scheduledTime, fetchImpl = fetch, sleep = (ms) => new Promise((r) => setTimeout(r, ms))) {
  const token = (env.GITHUB_DISPATCH_TOKEN || '').trim();
  if (!token) return 'not_configured';
  let request;
  try {
    request = dispatchRequest(env, scheduledTime);
  } catch {
    return 'invalid_configuration';
  }
  let result;
  for (let n = 1; n <= 2; n += 1) {
    result = await attempt(fetchImpl, request.url, token, request.body);
    if (result.status >= 200 && result.status < 300) return 'dispatched'; // normally 204
    if (result.status >= 400 && result.status < 500) return `rejected_http_${result.status}`;
    if (n === 1) await sleep(RETRY_DELAY_MS);
  }
  return result.status ? `failed_http_${result.status}` : `failed_${result.error}`;
}

export default {
  async scheduled(event, env, ctx) {
    const outcome = await dispatch(env, event.scheduledTime);
    console.log(`external trigger slot=${slotIso(event.scheduledTime)} outcome=${outcome}`);
    if (outcome !== 'dispatched') {
      // Surfaces as a failed invocation in Cloudflare's Cron Events; the GitHub cron remains as backup.
      throw new Error(`dispatch ${outcome}`);
    }
  },
};
