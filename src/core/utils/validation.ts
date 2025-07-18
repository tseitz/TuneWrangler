import { extname } from "https://deno.land/std@0.224.0/path/mod.ts";
import { FilePathError, UnsupportedFormatError, ConfigurationError, TuneWranglerError } from "./errors.ts";

/**
 * Supported audio file extensions
 */
export const SUPPORTED_AUDIO_EXTENSIONS = [".mp3", ".flac", ".wav", ".aiff", ".aif", ".m4a", ".ogg", ".opus"] as const;

export type SupportedAudioFormat = (typeof SUPPORTED_AUDIO_EXTENSIONS)[number];

/**
 * Validates that a file path exists and is accessible
 */
export async function validateFilePath(path: string, operation: string = "access"): Promise<void> {
  try {
    await Deno.stat(path);
  } catch (error) {
    if (error instanceof Deno.errors.NotFound) {
      throw new FilePathError(`File not found: ${path}`, path, operation);
    } else if (error instanceof Deno.errors.PermissionDenied) {
      throw new FilePathError(`Permission denied: ${path}`, path, operation);
    } else {
      throw new FilePathError(`Cannot access file: ${path}`, path, operation);
    }
  }
}

/**
 * Validates that a file is a supported audio format
 */
export function validateAudioFormat(filePath: string): SupportedAudioFormat {
  const extension = extname(filePath).toLowerCase();

  if (!SUPPORTED_AUDIO_EXTENSIONS.includes(extension as SupportedAudioFormat)) {
    throw new UnsupportedFormatError(`Unsupported audio format: ${extension}`, filePath, extension);
  }

  return extension as SupportedAudioFormat;
}

/**
 * Validates that a directory path exists and is writable
 */
export async function validateDirectory(path: string, operation: string = "write"): Promise<void> {
  try {
    const stat = await Deno.stat(path);
    if (!stat.isDirectory) {
      throw new FilePathError(`Path is not a directory: ${path}`, path, operation);
    }
  } catch (error) {
    if (error instanceof TuneWranglerError) {
      throw error;
    } else if (error instanceof Deno.errors.NotFound) {
      throw new FilePathError(`Directory not found: ${path}`, path, operation);
    } else if (error instanceof Deno.errors.PermissionDenied) {
      throw new FilePathError(`Permission denied: ${path}`, path, operation);
    } else {
      throw new FilePathError(`Cannot access directory: ${path}`, path, operation);
    }
  }
}

/**
 * Validates that a filename follows the expected format
 */
export function validateFilename(filename: string): void {
  if (!filename || filename.trim().length === 0) {
    throw new TuneWranglerError("Filename cannot be empty", "VALIDATION_ERROR");
  }

  // Check for invalid characters
  const invalidChars = /[<>:"/\\|?*]/;
  if (invalidChars.test(filename)) {
    throw new TuneWranglerError(`Filename contains invalid characters: ${filename}`, "VALIDATION_ERROR");
  }

  // Check for reserved names (Windows)
  const reservedNames = /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/i;
  if (reservedNames.test(filename)) {
    throw new TuneWranglerError(`Filename is a reserved name: ${filename}`, "VALIDATION_ERROR");
  }
}

/**
 * Validates that a configuration value is not empty
 */
export function validateConfigValue(value: string | undefined, key: string): string {
  if (!value || value.trim().length === 0) {
    throw new ConfigurationError(`Configuration value for '${key}' cannot be empty`, key, value);
  }
  return value;
}

/**
 * Validates that a URL is properly formatted
 */
export function validateUrl(url: string): URL {
  try {
    return new URL(url);
  } catch {
    throw new TuneWranglerError(`Invalid URL format: ${url}`, "VALIDATION_ERROR");
  }
}

/**
 * Validates that a number is within a valid range
 */
export function validateNumberRange(value: number, min: number, max: number, name: string): number {
  if (value < min || value > max) {
    throw new TuneWranglerError(`${name} must be between ${min} and ${max}, got: ${value}`, "VALIDATION_ERROR");
  }
  return value;
}

/**
 * Validates that a string is not empty and has minimum length
 */
export function validateString(value: string | undefined, name: string, minLength: number = 1): string {
  if (!value || value.trim().length < minLength) {
    throw new TuneWranglerError(`${name} must be at least ${minLength} character(s) long`, "VALIDATION_ERROR");
  }
  return value.trim();
}

/**
 * Validates that an array is not empty
 */
export function validateArray<T>(array: T[] | undefined, name: string): T[] {
  if (!array || array.length === 0) {
    throw new TuneWranglerError(`${name} cannot be empty`, "VALIDATION_ERROR");
  }
  return array;
}
