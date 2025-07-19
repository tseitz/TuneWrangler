# TuneWrangler API Reference

This document provides detailed API documentation for developers who want to extend TuneWrangler or integrate it into
their applications.

## Table of Contents

1. [Core Modules](#core-modules)
1. [Error Handling](#error-handling)
1. [Logging API](#logging-api)
1. [Validation API](#validation-api)
1. [Retry Mechanisms](#retry-mechanisms)
1. [CLI Framework](#cli-framework)
1. [Examples](#examples)
1. [Best Practices](#best-practices)

## Core Modules

### Configuration Management

#### `src/config/index.ts`

```typescript
import { loadConfig, PathConfig } from "../config/index.ts";

// Load configuration with platform detection
const config: PathConfig = loadConfig();

// Access specific paths
const musicDir = config.music;
const downloadsDir = config.downloads;
```

**Types:**

```typescript
export interface PathConfig {
  music: string;
  downloads: string;
  youtube: string;
  downloaded: string;
  itunes: string;
  djMusic: string;
  djPlaylists: string;
  djPlaylistImport: string;
  rename: string;
  backup: string;
  transfer: string;
}
```

**Functions:**

- `loadConfig()`: Load configuration with environment variable overrides
- `validatePaths(config: PathConfig)`: Validate all configured paths
- `getDefaultPaths(platform: string)`: Get platform-specific default paths

### Error Handling

#### `src/core/utils/errors.ts`

```typescript
import { 
  TuneWranglerError,
  FilePathError,
  AudioProcessingError,
  ConfigurationError,
  logError
} from "../core/utils/errors.ts";

// Create custom errors
throw new FilePathError("File not found", "/path/to/file.mp3");

// Log errors with context
try {
  // ... operation
} catch (error) {
  logError(error, { operation: "file processing", filename: "song.mp3" });
}
```

**Error Classes:**

- `TuneWranglerError`: Base error class
- `FilePathError`: File path and access errors
- `AudioProcessingError`: Audio file processing failures
- `MetadataError`: Metadata parsing failures
- `ConfigurationError`: Configuration validation errors
- `DuplicateError`: Duplicate file detection
- `UnsupportedFormatError`: Unsupported file format errors
- `NetworkError`: Network operation failures
- `PermissionError`: Permission denied errors

### Logging API

#### `src/core/utils/logger.ts`

```typescript
import { 
  getLogger, 
  configureLogger, 
  LogLevel,
  Logger,
  LoggerConfig 
} from "../core/utils/logger.ts";

// Get global logger
const logger = getLogger();

// Configure logging
configureLogger({
  level: LogLevel.DEBUG,
  enableConsole: true,
  enableFile: true,
  logDir: "./logs",
  format: "json"
});

// Log messages
logger.info("Processing started", { files: 100 });
logger.error("Operation failed", error, { context: "additional info" });

// Convenience methods
logger.startOperation("file processing");
logger.fileProcessed("song.mp3", "song_renamed.mp3");
logger.endOperation("file processing", { success: true });
```

**Log Levels:**

- `LogLevel.DEBUG` (0): Detailed debugging information
- `LogLevel.INFO` (1): General information
- `LogLevel.WARN` (2): Warning messages
- `LogLevel.ERROR` (3): Error messages
- `LogLevel.FATAL` (4): Critical errors

**Configuration:**

```typescript
interface LoggerConfig {
  level: LogLevel;
  enableConsole: boolean;
  enableFile: boolean;
  logDir: string;
  maxFileSize: number;
  maxFiles: number;
  format: "json" | "text";
}
```

### Validation API

#### `src/core/utils/validation.ts`

```typescript

import {
  validateFilePath,
  validateAudioFormat,
  validateDirectory,
  validateString,
  validateNumberRange,
  SupportedAudioFormat
} from "../core/utils/validation.ts";

// Validate file paths
await validateFilePath("/path/to/file.mp3", "read");
await validateDirectory("/path/to/directory", "write");

// Validate audio formats
const format = validateAudioFormat("/path/to/file.mp3");
if (format === SupportedAudioFormat.MP3) {
  // Process MP3 file
}

// Validate data
const title = validateString(songTitle, "title", 1, 255);
const rating = validateNumberRange(songRating, 1, 5, "rating");
```

**Supported Audio Formats:**

```typescript
enum SupportedAudioFormat {
  MP3 = "mp3",
  FLAC = "flac",
  AAC = "aac",
  OGG = "ogg",
  WAV = "wav",
  M4A = "m4a"
}
```

### Retry Mechanisms

#### `src/core/utils/retry.ts`

```typescript
import {
  withRetry,
  withFileRetry,
  withNetworkRetry,
  withAudioRetry,
  RetryOptions
} from "../core/utils/retry.ts";

// Generic retry
const result = await withRetry(async () => {
  return await someOperation();
}, { maxAttempts: 3, delayMs: 1000 });

// File operation retry
const content = await withFileRetry(async () => {
  return await Deno.readTextFile("/path/to/file");
}, "/path/to/file");

// Network operation retry
const response = await withNetworkRetry(async () => {
  return await fetch("https://api.example.com/data");
}, "https://api.example.com/data");

// Audio processing retry
const processed = await withAudioRetry(async () => {
  return await processAudioFile("/path/to/audio.mp3");
}, "/path/to/audio.mp3");
```

**Retry Options:**

```typescript
interface RetryOptions {
  maxAttempts: number;
  delayMs: number;
  backoffMultiplier: number;
  maxDelayMs: number;
}
```

## CLI Framework

### Command Structure

#### `src/cli/main.ts`

```typescript
import { Command } from "../cli/main.ts";

// Define a new command
const myCommand: Command = {
  name: "my-command",
  description: "My custom command",
  usage: "tunewrangler my-command [options]",
  examples: [
    "tunewrangler my-command --input /path",
    "tunewrangler my-command --help"
  ],
  execute: async (args: string[]) => {
    // Command implementation
  }
};

// Add to commands object
const commands = {
  // ... existing commands
  "my-command": myCommand
};
```

### Command Implementation

#### `src/cli/commands/example.ts`

```typescript
import { parse } from "https://deno.land/std@0.224.0/flags/mod.ts";
import { getLogger } from "../../core/utils/logger.ts";

export async function exampleCommand(args: string[]): Promise<void> {
  const logger = getLogger();
  
  // Parse command flags
  const flags = parse(args, {
    boolean: ["help", "verbose"],
    string: ["input", "output"],
    alias: { help: "h" }
  });

  if (flags.help) {
    console.log(`
🎵 TuneWrangler example-command

Description of what this command does.

USAGE:
  tunewrangler example-command [options]

OPTIONS:
  --help, -h        Show this help message
  --input <path>    Input directory
  --output <path>   Output directory
  --verbose         Enable verbose output

EXAMPLES:
  tunewrangler example-command --input /music --output /organized
  tunewrangler example-command --help
`);
    return;
  }

  logger.startOperation("example command", { flags });

  try {
    // Command logic here
    const inputPath = flags.input;
    const outputPath = flags.output;

    if (!inputPath || !outputPath) {
      throw new Error("Input and output paths are required");
    }

    // Process files
    logger.info("Processing files", { input: inputPath, output: outputPath });
    
    // ... implementation ...

    logger.endOperation("example command", { success: true });
  } catch (error) {
    logger.error("Example command failed", error as Error);
    throw error;
  }
}
```

## Examples

### Custom Music Processor

```typescript
// src/processors/customProcessor.ts
import { 
  getLogger, 
  validateFilePath, 
  validateAudioFormat,
  withAudioRetry,
  AudioProcessingError 
} from "../core/utils/index.ts";

export class CustomMusicProcessor {
  private logger = getLogger();

  async processFile(filePath: string, outputPath: string): Promise<void> {
    this.logger.startOperation("custom music processing", { 
      input: filePath, 
      output: outputPath 
    });

    try {
      // Validate input
      await validateFilePath(filePath, "read");
      const format = validateAudioFormat(filePath);
      
      this.logger.processingFile(filePath, { format });

      // Process with retry
      const result = await withAudioRetry(async () => {
        return await this.performProcessing(filePath, outputPath);
      }, filePath);

      this.logger.fileProcessed(filePath, outputPath, { result });
      this.logger.endOperation("custom music processing", { success: true });

    } catch (error) {
      this.logger.fileError(filePath, error as Error);
      throw new AudioProcessingError(`Failed to process ${filePath}`, error as Error);
    }
  }

  private async performProcessing(input: string, output: string): Promise<string> {
    // Custom processing logic here
    // This could involve:
    // - Audio analysis
    // - Metadata extraction
    // - Format conversion
    // - Quality enhancement
    
    return output;
  }
}
```

### Configuration Extension

```typescript
// src/config/customConfig.ts
import { PathConfig, loadConfig } from "./index.ts";

export interface ExtendedPathConfig extends PathConfig {
  customPath: string;
  processingPath: string;
}

export function loadExtendedConfig(): ExtendedPathConfig {
  const baseConfig = loadConfig();
  
  return {
    ...baseConfig,
    customPath: Deno.env.get("TUNEWRANGLER_CUSTOM_PATH") || 
                `${baseConfig.music}Custom/`,
    processingPath: Deno.env.get("TUNEWRANGLER_PROCESSING_PATH") || 
                   `${baseConfig.transfer}Processing/`
  };
}
```

### Custom Error Handler

```typescript
// src/core/utils/customErrors.ts
import { TuneWranglerError } from "./errors.ts";

export class CustomProcessingError extends TuneWranglerError {
  constructor(
    message: string,
    public readonly customContext?: Record<string, unknown>
  ) {
    super(message, "CustomProcessingError");
    this.name = "CustomProcessingError";
  }
}

export class ValidationError extends TuneWranglerError {
  constructor(
    message: string,
    public readonly field: string,
    public readonly value: unknown
  ) {
    super(message, "ValidationError");
    this.name = "ValidationError";
  }
}
```

### Integration Example

```typescript
// src/integrations/example.ts
import { 
  getLogger, 
  configureLogger, 
  LogLevel,
  loadConfig,
  validateConfiguration 
} from "../core/utils/index.ts";

export class TuneWranglerIntegration {
  private logger = getLogger();

  constructor() {
    // Configure logging for integration
    configureLogger({
      level: LogLevel.INFO,
      enableConsole: true,
      enableFile: true,
      logDir: "./logs",
      format: "json"
    });
  }

  async initialize(): Promise<void> {
    this.logger.startOperation("TuneWrangler integration initialization");

    try {
      // Load and validate configuration
      const config = loadConfig();
      const isValid = await validateConfiguration();
      
      if (!isValid) {
        throw new Error("Configuration validation failed");
      }

      this.logger.configurationLoaded(config);
      this.logger.endOperation("TuneWrangler integration initialization", { success: true });

    } catch (error) {
      this.logger.error("Integration initialization failed", error as Error);
      throw error;
    }
  }

  async processMusicLibrary(): Promise<void> {
    this.logger.startOperation("music library processing");

    try {
      // Your custom processing logic here
      // This could integrate with external services,
      // databases, or other applications

      this.logger.endOperation("music library processing", { success: true });

    } catch (error) {
      this.logger.error("Music library processing failed", error as Error);
      throw error;
    }
  }
}
```

## Best Practices

### Error Handling Best Practices

1. **Use specific error types**: Always use the most specific error class for your use case
2. **Include context**: Provide meaningful context with errors
3. **Log errors properly**: Use the logging system for error tracking
4. **Handle gracefully**: Provide fallbacks when possible

```typescript
try {
  await processFile(filePath);
} catch (error) {
  if (error instanceof FilePathError) {
    // Handle file path issues
    logger.warn("File path issue", { path: filePath, error: error.message });
  } else if (error instanceof AudioProcessingError) {
    // Handle audio processing issues
    logger.error("Audio processing failed", error, { file: filePath });
  } else {
    // Handle unexpected errors
    logger.fatal("Unexpected error", error, { operation: "file processing" });
  }
}
```

### Logging

1. **Use appropriate levels**: DEBUG for development, INFO for operations, ERROR for issues
2. **Include context**: Always include relevant context with log messages
3. **Use convenience methods**: Use built-in convenience methods for common operations
4. **Structure data**: Use structured logging for better analysis

```typescript
// Good logging
logger.info("File processed", {
  filename: "song.mp3",
  size: 1024,
  duration: "3:45",
  artist: "Artist Name",
  album: "Album Name"
});

// Use convenience methods
logger.startOperation("batch processing", { files: fileCount });
logger.fileProcessed(filename, newFilename);
logger.endOperation("batch processing", { success: true, processed: processedCount });
```

### Configuration

1. **Validate early**: Always validate configuration at startup
2. **Use environment variables**: Prefer environment variables over hardcoded values
3. **Provide defaults**: Always provide sensible defaults
4. **Document options**: Document all configuration options

### Performance

1. **Use retry mechanisms**: Use built-in retry mechanisms for unreliable operations
2. **Process in batches**: Process files in batches rather than one at a time
3. **Monitor resources**: Use logging to monitor performance and resource usage
4. **Handle large datasets**: Implement pagination or streaming for large datasets

---

For more information, see the [User Guide](USER_GUIDE.md) and [Troubleshooting Guide](TROUBLESHOOTING.md).
