# TuneWrangler Core Utilities

This directory contains the core utilities for TuneWrangler, including error handling, validation, retry mechanisms, and
logging.

## Logging System

The logging system provides structured, configurable logging with multiple output formats and levels.

### Features

- **Multiple Log Levels**: DEBUG, INFO, WARN, ERROR, FATAL
- **Console Output**: Colored, formatted output for development
- **File Output**: Persistent logs with automatic rotation
- **Structured Logging**: JSON and text formats
- **Context Support**: Additional metadata with each log entry
- **Error Tracking**: Automatic error stack traces
- **Log Management**: Built-in CLI commands for log management

### Quick Start

```typescript
import { getLogger, info, error, LogLevel } from "../core/utils/logger.ts";

// Get the global logger
const logger = getLogger();

// Basic logging
logger.info("Processing started");
logger.error("Something went wrong", new Error("Details"));

// Convenience functions
info("Quick info message");
error("Quick error message", new Error("Details"));

// With context
logger.info("File processed", { filename: "song.mp3", size: 1024 });
```

### Configuration

```typescript
import { configureLogger, LogLevel } from "../core/utils/logger.ts";

// Configure global logger
configureLogger({
  level: LogLevel.DEBUG,        // Minimum log level
  enableConsole: true,          // Show logs in console
  enableFile: true,             // Save logs to file
  logDir: "./logs",             // Log directory
  maxFileSize: 10 * 1024 * 1024, // 10MB max file size
  maxFiles: 5,                  // Keep 5 log files
  format: "text",               // "text" or "json"
});
```

### Log Levels

- **DEBUG (0)**: Detailed information for debugging
- **INFO (1)**: General information about program execution
- **WARN (2)**: Warning messages for potential issues
- **ERROR (3)**: Error messages for recoverable errors
- **FATAL (4)**: Critical errors that may cause program termination

### Convenience Methods

The logger provides specialized methods for common operations:

```typescript
// Operation tracking
logger.startOperation("file processing", { filename: "song.mp3" });
logger.endOperation("file processing", { success: true });

// File operations
logger.processingFile("song.mp3");
logger.fileProcessed("song.mp3", "song_renamed.mp3");
logger.fileSkipped("song.mp3", "already exists");
logger.fileError("song.mp3", new Error("Permission denied"));

// Duplicate detection
logger.duplicateFound("song_copy.mp3", "song.mp3");

// Configuration
logger.configurationLoaded({ musicDir: "/music" });
logger.configurationError("Invalid path", { path: "/invalid" });
```

### CLI Integration

The logging system is automatically integrated with the CLI:

```bash
# Normal logging (INFO level)
./tunewrangler validate

# Verbose logging (DEBUG level)
./tunewrangler --verbose validate

# Quiet mode (ERROR level only)
./tunewrangler --quiet validate
```

### Log Management

Use the built-in `logs` command to manage log files:

```bash
# List all log files
./tunewrangler logs --list

# Show last 50 lines of current log
./tunewrangler logs --tail

# Show specific log file
./tunewrangler logs --file tunewrangler-2025-07-18.log

# Clear all log files
./tunewrangler logs --clear
```

### Log File Format

Log files are automatically created with the format: `tunewrangler-YYYY-MM-DD.log`

**Text Format Example:**

```bash
[2025-07-18T16:42:22.639Z] INFO: 🚀 Starting operation: TuneWrangler CLI
  Context: { args: [ "logs" ] }
[2025-07-18T16:42:22.641Z] INFO: 🚀 Starting operation: logs command
  Context: { flags: { _: [], tail: true, help: false } }
```

**JSON Format Example:**

```json
{"timestamp":"2025-07-18T16:42:22.639Z","level":"INFO","message":"🚀 Starting operation: TuneWrangler CLI","context":{"args":["logs"]}}
{"timestamp":"2025-07-18T16:42:22.641Z","level":"INFO","message":"🚀 Starting operation: logs command","context":{"flags":{"_":[],"tail":true,"help":false}}}
```

### Automatic Log Rotation

- Log files are automatically rotated when they exceed the maximum size
- Old log files are automatically deleted when the maximum number is reached
- Log files are created daily with date-based naming

### Best Practices

1. **Use Appropriate Levels**: Use DEBUG for development, INFO for normal operations, WARN for potential issues,
ERROR for recoverable errors, FATAL for critical failures.

2. **Include Context**: Always include relevant context with your log messages:

   ```typescript
   logger.info("File processed", { 
     filename: "song.mp3", 
     size: 1024, 
     duration: "3:45" 
   });
   ```

3. **Log Errors Properly**: Always pass the error object to error logging:

   ```typescript
   try {
     // ... operation
   } catch (error) {
     logger.error("Operation failed", error, { operation: "file processing" });
   }
   ```

4. **Use Convenience Methods**: Use the built-in convenience methods for common operations to ensure consistent logging.

5. **Configure Appropriately**: In production, consider:
   - Setting log level to INFO or WARN
   - Enabling file logging
   - Using JSON format for better parsing
   - Setting appropriate file size and count limits

### Integration with Other Systems

The logging system can be easily extended to integrate with external logging services:

```typescript
class CustomLogger extends Logger {
  async writeLog(entry: LogEntry): Promise<void> {
    // Call parent implementation
    await super.writeLog(entry);
    
    // Send to external service
    await this.sendToExternalService(entry);
  }
  
  private async sendToExternalService(entry: LogEntry): Promise<void> {
    // Implementation for external service
  }
}

// Use custom logger
setLogger(new CustomLogger());
```

### Performance Considerations

- Logging is asynchronous and won't block your application
- File I/O is buffered for better performance
- Log rotation happens in the background
- Context objects are serialized only when needed

### Troubleshooting

**Logs not appearing:**

- Check log level configuration
- Verify console/file output is enabled
- Check file permissions for log directory

**Large log files:**

- Adjust `maxFileSize` configuration
- Reduce `maxFiles` count
- Use appropriate log levels

**Missing context:**

- Ensure context objects are serializable
- Check for circular references in context objects
