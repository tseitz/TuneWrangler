/**
 * Base error class for TuneWrangler application
 */
export class TuneWranglerError extends Error {
  constructor(message: string, public readonly code: string, public readonly details?: Record<string, unknown>) {
    super(message);
    this.name = "TuneWranglerError";
  }
}

/**
 * Error thrown when a file path is invalid or doesn't exist
 */
export class FilePathError extends TuneWranglerError {
  constructor(message: string, public readonly path: string, public readonly operation: string) {
    super(message, "FILE_PATH_ERROR", { path, operation });
    this.name = "FilePathError";
  }
}

/**
 * Error thrown when audio file processing fails
 */
export class AudioProcessingError extends TuneWranglerError {
  constructor(
    message: string,
    public readonly filePath: string,
    public readonly operation: string,
    public readonly originalError?: Error
  ) {
    super(message, "AUDIO_PROCESSING_ERROR", { filePath, operation });
    this.name = "AudioProcessingError";
  }
}

/**
 * Error thrown when metadata parsing fails
 */
export class MetadataError extends TuneWranglerError {
  constructor(message: string, public readonly filePath: string, public readonly metadataType: string) {
    super(message, "METADATA_ERROR", { filePath, metadataType });
    this.name = "MetadataError";
  }
}

/**
 * Error thrown when configuration is invalid
 */
export class ConfigurationError extends TuneWranglerError {
  constructor(message: string, public readonly configKey?: string, public readonly configValue?: string) {
    super(message, "CONFIGURATION_ERROR", { configKey, configValue });
    this.name = "ConfigurationError";
  }
}

/**
 * Error thrown when duplicate files are detected
 */
export class DuplicateError extends TuneWranglerError {
  constructor(message: string, public readonly originalFile: string, public readonly duplicateFile: string) {
    super(message, "DUPLICATE_ERROR", { originalFile, duplicateFile });
    this.name = "DuplicateError";
  }
}

/**
 * Error thrown when file format is not supported
 */
export class UnsupportedFormatError extends TuneWranglerError {
  constructor(message: string, public readonly filePath: string, public readonly format: string) {
    super(message, "UNSUPPORTED_FORMAT_ERROR", { filePath, format });
    this.name = "UnsupportedFormatError";
  }
}

/**
 * Error thrown when network operations fail
 */
export class NetworkError extends TuneWranglerError {
  constructor(message: string, public readonly url?: string, public readonly statusCode?: number) {
    super(message, "NETWORK_ERROR", { url, statusCode });
    this.name = "NetworkError";
  }
}

/**
 * Error thrown when permission is denied
 */
export class PermissionError extends TuneWranglerError {
  constructor(message: string, public readonly path: string, public readonly operation: string) {
    super(message, "PERMISSION_ERROR", { path, operation });
    this.name = "PermissionError";
  }
}

/**
 * Utility function to check if an error is a TuneWranglerError
 */
export function isTuneWranglerError(error: unknown): error is TuneWranglerError {
  return error instanceof TuneWranglerError;
}

/**
 * Utility function to get a user-friendly error message
 */
export function getErrorMessage(error: unknown): string {
  if (isTuneWranglerError(error)) {
    return `${error.name}: ${error.message}`;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return String(error);
}

/**
 * Error thrown when performance operations fail
 */
export class PerformanceError extends TuneWranglerError {
  constructor(message: string, public readonly operation?: string, public readonly metrics?: Record<string, unknown>) {
    super(message, "PERFORMANCE_ERROR", { operation, metrics });
    this.name = "PerformanceError";
  }
}

/**
 * Utility function to log errors with context
 */
export function logError(error: unknown, context?: Record<string, unknown>): void {
  const message = getErrorMessage(error);
  const details = isTuneWranglerError(error) ? error.details : {};

  console.error("❌ Error:", message);

  if ((details && Object.keys(details).length > 0) || context) {
    console.error("📋 Details:", { ...(details || {}), ...(context || {}) });
  }

  if (error instanceof Error && error.stack) {
    console.error("🔍 Stack trace:", error.stack);
  }
}
