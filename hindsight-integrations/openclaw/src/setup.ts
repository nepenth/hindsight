#!/usr/bin/env node
/**
 * Interactive setup wizard for the Hindsight OpenClaw plugin.
 *
 * Walks the user through picking a mode (Cloud / External API / Embedded daemon)
 * and writes the resulting plugin config into ~/.openclaw/openclaw.json.
 *
 * Scanner-safe: does not import subprocess APIs and does not read environment
 * variables directly. Pure config manipulation lives in setup-lib.ts and is
 * unit tested separately.
 */

import * as p from '@clack/prompts';
import {
  DEFAULT_OPENCLAW_CONFIG_PATH,
  HINDSIGHT_CLOUD_URL,
  NO_KEY_PROVIDERS,
  applyApiMode,
  applyCloudMode,
  applyEmbeddedMode,
  defaultApiKeyEnvVar,
  ensurePluginConfig,
  isValidEnvVarName,
  loadConfig,
  saveConfig,
  summarizeApi,
  summarizeCloud,
  summarizeEmbedded,
  type SetupMode,
} from './setup-lib.js';

const validateEnvVar = (value: string | undefined): string | undefined =>
  isValidEnvVarName(value) ? undefined : 'Must be an UPPER_SNAKE_CASE env var name';

const validateRequired =
  (msg: string) =>
  (value: string | undefined): string | undefined =>
    value && value.trim().length > 0 ? undefined : msg;

function assertNotCancelled<T>(value: T | symbol): asserts value is T {
  if (p.isCancel(value)) {
    p.cancel('Setup cancelled.');
    process.exit(1);
  }
}

async function promptCloud(pluginConfig: Record<string, unknown>): Promise<string> {
  const useDefaultUrl = await p.confirm({
    message: `Use the default Hindsight Cloud URL (${HINDSIGHT_CLOUD_URL})?`,
    initialValue: true,
  });
  assertNotCancelled(useDefaultUrl);

  let apiUrl: string | undefined;
  if (!useDefaultUrl) {
    const custom = await p.text({
      message: 'Hindsight Cloud URL',
      placeholder: HINDSIGHT_CLOUD_URL,
      validate: validateRequired('URL is required'),
    });
    assertNotCancelled(custom);
    apiUrl = custom;
  }

  const tokenEnvVar = await p.text({
    message: 'Environment variable holding your Hindsight Cloud API token',
    placeholder: 'HINDSIGHT_CLOUD_TOKEN',
    initialValue: 'HINDSIGHT_CLOUD_TOKEN',
    validate: validateEnvVar,
  });
  assertNotCancelled(tokenEnvVar);

  const input = { apiUrl, tokenEnvVar };
  applyCloudMode(pluginConfig, input);
  return summarizeCloud(input);
}

async function promptApi(pluginConfig: Record<string, unknown>): Promise<string> {
  const apiUrl = await p.text({
    message: 'Hindsight API URL',
    placeholder: 'https://mcp.hindsight.example.com',
    validate: validateRequired('URL is required'),
  });
  assertNotCancelled(apiUrl);

  const needsToken = await p.confirm({
    message: 'Does this API require an auth token?',
    initialValue: false,
  });
  assertNotCancelled(needsToken);

  let tokenEnvVar: string | undefined;
  if (needsToken) {
    const value = await p.text({
      message: 'Environment variable holding the API token',
      placeholder: 'HINDSIGHT_API_TOKEN',
      initialValue: 'HINDSIGHT_API_TOKEN',
      validate: validateEnvVar,
    });
    assertNotCancelled(value);
    tokenEnvVar = value;
  }

  const input = { apiUrl, tokenEnvVar };
  applyApiMode(pluginConfig, input);
  return summarizeApi(input);
}

async function promptEmbedded(pluginConfig: Record<string, unknown>): Promise<string> {
  const provider = await p.select({
    message: 'LLM provider used by the Hindsight memory daemon',
    options: [
      { value: 'openai', label: 'OpenAI', hint: 'API key required' },
      { value: 'anthropic', label: 'Anthropic', hint: 'API key required' },
      { value: 'gemini', label: 'Gemini', hint: 'API key required' },
      { value: 'groq', label: 'Groq', hint: 'API key required' },
      {
        value: 'claude-code',
        label: 'Claude Code',
        hint: 'no API key needed (uses Claude Code CLI auth)',
      },
      {
        value: 'openai-codex',
        label: 'OpenAI Codex',
        hint: 'no API key needed (uses codex auth login)',
      },
      { value: 'ollama', label: 'Ollama', hint: 'no API key needed (local models)' },
    ],
  });
  assertNotCancelled(provider);
  const llmProvider = provider as string;

  let apiKeyEnvVar: string | undefined;
  if (!NO_KEY_PROVIDERS.has(llmProvider)) {
    const defaultEnvId = defaultApiKeyEnvVar(llmProvider);
    const envId = await p.text({
      message: `Environment variable holding your ${llmProvider} API key`,
      placeholder: defaultEnvId,
      initialValue: defaultEnvId,
      validate: validateEnvVar,
    });
    assertNotCancelled(envId);
    apiKeyEnvVar = envId;
  }

  const overrideModel = await p.confirm({
    message: 'Override the default model?',
    initialValue: false,
  });
  assertNotCancelled(overrideModel);

  let llmModel: string | undefined;
  if (overrideModel) {
    const value = await p.text({
      message: 'Model id',
      placeholder: 'gpt-4o-mini',
      validate: validateRequired('Model id is required'),
    });
    assertNotCancelled(value);
    llmModel = value;
  }

  const input = { llmProvider, apiKeyEnvVar, llmModel };
  applyEmbeddedMode(pluginConfig, input);
  return summarizeEmbedded(input);
}

async function main(): Promise<void> {
  p.intro('🦞 Hindsight Memory setup for OpenClaw');

  // Optional first positional arg overrides the config path (useful for
  // non-default OpenClaw profiles or scripted testing).
  const configPath =
    process.argv[2] && process.argv[2].trim().length > 0
      ? process.argv[2]
      : DEFAULT_OPENCLAW_CONFIG_PATH;
  p.log.info(`Config file: ${configPath}`);

  const cfg = await loadConfig(configPath);
  const pluginConfig = ensurePluginConfig(cfg);

  const mode = await p.select({
    message: 'How do you want to run Hindsight?',
    options: [
      { value: 'cloud', label: 'Cloud', hint: 'managed Hindsight, no local setup' },
      { value: 'api', label: 'External API', hint: 'your own running Hindsight deployment' },
      {
        value: 'embedded',
        label: 'Embedded daemon',
        hint: 'spawn a local hindsight daemon on this machine',
      },
    ],
  });
  assertNotCancelled(mode);

  let summary: string;
  if ((mode as SetupMode) === 'cloud') {
    summary = await promptCloud(pluginConfig);
  } else if ((mode as SetupMode) === 'api') {
    summary = await promptApi(pluginConfig);
  } else {
    summary = await promptEmbedded(pluginConfig);
  }

  const spin = p.spinner();
  spin.start('Writing configuration');
  await saveConfig(configPath, cfg);
  spin.stop(`Saved to ${configPath}`);

  p.note(
    [
      summary,
      '',
      'Next steps:',
      '  1. Ensure any referenced env vars are exported in the shell that runs the gateway.',
      '  2. Restart the gateway:  openclaw gateway restart',
      '  3. Verify config:        openclaw config validate',
    ].join('\n'),
    'Hindsight Memory configured',
  );
  p.outro('Done.');
}

main().catch((err: unknown) => {
  const msg = err instanceof Error ? err.message : String(err);
  console.error(`hindsight-openclaw-setup failed: ${msg}`);
  process.exit(1);
});
