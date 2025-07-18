# Core Utilities

This module provides comprehensive error handling, validation, and utility functions for the TuneWrangler application.

## Error Handling

### Custom Error Types

The application uses custom error types for different failure scenarios:

- **`TuneWranglerError`** - Base error class for all application errors
- **`FilePathError`** - File path validation and access errors
- **`AudioProcessingError`** - Audio file processing failures
- **`MetadataError`** - Metadata parsing failures
- **`ConfigurationError`** - Configuration validation errors
- **`DuplicateError`** - Duplicate file detection
- **`UnsupportedFormatError`** - Unsupported file format errors
- **`NetworkError`** - Network operation failures
- **`PermissionError`** - Permission denied errors

### Error Logging

```typescript
import { logError } from "../core/utils/errors.ts";

try {
  // Some operation
} catch (error) {
  logError(error, { context: "additional info" });
}
```

## Input Validation

### File Validation

```typescript
import { validateFilePath, validateAudioFormat, validateDirectory } from "../core/utils/validation.ts";

// Validate file exists and is accessible
await validateFilePath("/path/to/file.mp3", "read");

// Validate audio format
const format = validateAudioFormat("/path/to/file.mp3");

// Validate directory exists and is writable
await validateDirectory("/path/to/directory", "write");
```

### Data Validation

```typescript
import { validateString, validateNumberRange, validateArray } from "../core/utils/validation.ts";

// Validate string
const title = validateString(songTitle, "title", 1);

// Validate number range
const rating = validateNumberRange(songRating, 1, 5, "rating");

// Validate array
const artists = validateArray(songArtists, "artists");
```

## Retry Mechanism

The application includes retry logic for operations that might fail due to temporary issues:

```typescript
import { withRetry, withFileRetry, withNetworkRetry } from "../core/utils/retry.ts";

// Generic retry
const result = await withRetry(async () => {
  return await someOperation();
}, { maxAttempts: 3, delayMs: 1000 });

// File operation retry
const fileContent = await withFileRetry(async () => {
  return await Deno.readTextFile("/path/to/file");
}, "/path/to/file");

// Network operation retry
const response = await withNetworkRetry(async () => {
  return await fetch("https://api.example.com/data");
}, "https://api.example.com/data");
```

## Usage Examples

### Processing a Music File

```typescript
import { 
  validateAudioFormat, 
  validateFilePath, 
  AudioProcessingError,
  withAudioRetry 
} from "../core/utils/index.ts";

async function processMusicFile(filePath: string) {
  try {
    // Validate file exists
    await validateFilePath(filePath, "process");
    
    // Validate audio format
    const format = validateAudioFormat(filePath);
    
    // Process with retry
    const result = await withAudioRetry(async () => {
      return await convertAudio(filePath);
    }, filePath);
    
    return result;
  } catch (error) {
    if (error instanceof AudioProcessingError) {
      console.error(`Failed to process ${filePath}:`, error.message);
    } else {
      console.error("Unexpected error:", error);
    }
    throw error;
  }
}
```

### Configuration Validation

```typescript
import { 
  validateConfiguration, 
  ConfigurationError 
} from "../core/utils/index.ts";

async function startApplication() {
  try {
    const isValid = await validateConfiguration();
    if (!isValid) {
      throw new ConfigurationError("Configuration validation failed");
    }
    
    // Continue with application startup
  } catch (error) {
    if (error instanceof ConfigurationError) {
      console.error("Configuration error:", error.message);
      process.exit(1);
    }
    throw error;
  }
}
```

## Best Practices

1. **Always validate inputs** before processing
2. **Use specific error types** for better error handling
3. **Log errors with context** for debugging
4. **Use retry mechanisms** for transient failures
5. **Handle errors gracefully** with user-friendly messages
6. **Validate configuration** at startup

## Error Recovery

The system provides several recovery mechanisms:

- **Automatic retries** for transient failures
- **Graceful degradation** when non-critical operations fail
- **Detailed error logging** for debugging
- **User-friendly error messages** for common issues 
