import { logError } from "./errors.ts";

export interface RetryOptions {
  maxAttempts: number;
  delayMs: number;
  backoffMultiplier: number;
  maxDelayMs: number;
}

export const DEFAULT_RETRY_OPTIONS: RetryOptions = {
  maxAttempts: 3,
  delayMs: 1000,
  backoffMultiplier: 2,
  maxDelayMs: 10000,
};

/**
 * Executes a function with retry logic
 */
export async function withRetry<T>(operation: () => Promise<T>, options: Partial<RetryOptions> = {}): Promise<T> {
  const config = { ...DEFAULT_RETRY_OPTIONS, ...options };
  let lastError: Error;

  for (let attempt = 1; attempt <= config.maxAttempts; attempt++) {
    try {
      return await operation();
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));

      // Don't retry on the last attempt
      if (attempt === config.maxAttempts) {
        throw lastError;
      }

      // Log the error but continue retrying
      logError(lastError, {
        attempt,
        maxAttempts: config.maxAttempts,
        operation: operation.name || "unknown",
      });

      // Calculate delay with exponential backoff
      const delay = Math.min(config.delayMs * Math.pow(config.backoffMultiplier, attempt - 1), config.maxDelayMs);

      console.log(`⏳ Retrying in ${delay}ms... (attempt ${attempt}/${config.maxAttempts})`);
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  // This should never be reached, but TypeScript needs it
  throw lastError!;
}

/**
 * Executes a function with retry logic for file operations
 */
export async function withFileRetry<T>(operation: () => Promise<T>, filePath: string): Promise<T> {
  return withRetry(operation, {
    maxAttempts: 5,
    delayMs: 500,
    backoffMultiplier: 1.5,
    maxDelayMs: 5000,
  });
}

/**
 * Executes a function with retry logic for network operations
 */
export async function withNetworkRetry<T>(operation: () => Promise<T>, url?: string): Promise<T> {
  return withRetry(operation, {
    maxAttempts: 3,
    delayMs: 2000,
    backoffMultiplier: 2,
    maxDelayMs: 15000,
  });
}

/**
 * Executes a function with retry logic for audio processing
 */
export async function withAudioRetry<T>(operation: () => Promise<T>, filePath: string): Promise<T> {
  return withRetry(operation, {
    maxAttempts: 2,
    delayMs: 1000,
    backoffMultiplier: 1,
    maxDelayMs: 2000,
  });
}
