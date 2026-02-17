import { join } from "@std/path";
import { ensureDir } from "@std/fs";

export enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3,
  FATAL = 4,
}

export interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
  context?: Record<string, unknown>;
  error?: Error;
}

export interface LoggerConfig {
  level: LogLevel;
  enableConsole: boolean;
  enableFile: boolean;
  logDir: string;
  maxFileSize: number; // in bytes
  maxFiles: number;
  format: "json" | "text";
}

export class Logger {
  private config: LoggerConfig;
  private logFile?: Deno.FsFile;
  private currentLogFile: string = "";

  constructor(config: Partial<LoggerConfig> = {}) {
    this.config = {
      level: LogLevel.INFO,
      enableConsole: true,
      enableFile: false,
      logDir: "./logs",
      maxFileSize: 10 * 1024 * 1024, // 10MB
      maxFiles: 5,
      format: "text",
      ...config,
    };

    if (this.config.enableFile) {
      this.ensureLogDirectory();
      this.rotateLogFile();
    }
  }

  private async ensureLogDirectory(): Promise<void> {
    await ensureDir(this.config.logDir);
  }

  private getLogFileName(): string {
    const date = new Date().toISOString().split("T")[0];
    return `tunewrangler-${date}.log`;
  }

  private async rotateLogFile(): Promise<void> {
    const logFileName = this.getLogFileName();
    const logFilePath = join(this.config.logDir, logFileName);

    // Close existing log file
    if (this.logFile) {
      this.logFile.close();
    }

    // Check if we need to rotate based on file size
    try {
      const stat = await Deno.stat(logFilePath);
      if (stat.size > this.config.maxFileSize) {
        await this.rotateOldLogs();
      }
    } catch {
      // File doesn't exist, that's fine
    }

    // Open new log file
    this.logFile = await Deno.open(logFilePath, {
      write: true,
      append: true,
      create: true,
    });

    this.currentLogFile = logFilePath;
  }

  private async rotateOldLogs(): Promise<void> {
    const files: Array<{ name: string; size: number; modified: Date }> = [];

    // Get all log files
    for await (const entry of Deno.readDir(this.config.logDir)) {
      if (entry.isFile && entry.name.startsWith("tunewrangler-") && entry.name.endsWith(".log")) {
        const filePath = join(this.config.logDir, entry.name);
        const stat = await Deno.stat(filePath);
        files.push({
          name: entry.name,
          size: stat.size,
          modified: stat.mtime || new Date(),
        });
      }
    }

    // Sort by modification time (oldest first)
    files.sort((a, b) => a.modified.getTime() - b.modified.getTime());

    // Remove oldest files if we have too many
    while (files.length >= this.config.maxFiles) {
      const oldest = files.shift();
      if (oldest) {
        const filePath = join(this.config.logDir, oldest.name);
        try {
          await Deno.remove(filePath);
        } catch {
          // Ignore errors if file doesn't exist
        }
      }
    }
  }

  private formatLogEntry(entry: LogEntry): string {
    const timestamp = entry.timestamp;
    const level = LogLevel[entry.level];
    const message = entry.message;
    const context = entry.context ? ` ${JSON.stringify(entry.context)}` : "";
    const error = entry.error ? `\n${entry.error.stack || entry.error.message}` : "";

    if (this.config.format === "json") {
      return (
        JSON.stringify({
          timestamp: entry.timestamp,
          level: LogLevel[entry.level],
          message: entry.message,
          context: entry.context,
          error: entry.error
            ? {
                message: entry.error.message,
                stack: entry.error.stack,
              }
            : undefined,
        }) + "\n"
      );
    } else {
      return `[${timestamp}] ${level}: ${message}${context}${error}\n`;
    }
  }

  private async writeLog(entry: LogEntry): Promise<void> {
    const formatted = this.formatLogEntry(entry);

    // Console output
    if (this.config.enableConsole) {
      const colors = {
        [LogLevel.DEBUG]: "\x1b[36m", // Cyan
        [LogLevel.INFO]: "\x1b[32m", // Green
        [LogLevel.WARN]: "\x1b[33m", // Yellow
        [LogLevel.ERROR]: "\x1b[31m", // Red
        [LogLevel.FATAL]: "\x1b[35m", // Magenta
      };
      const reset = "\x1b[0m";

      const levelName = LogLevel[entry.level];
      const coloredLevel = `${colors[entry.level]}${levelName}${reset}`;
      const coloredMessage = `${colors[entry.level]}${entry.message}${reset}`;

      console.log(`[${entry.timestamp}] ${coloredLevel}: ${coloredMessage}`);

      if (entry.context && Object.keys(entry.context).length > 0) {
        console.log(`  Context:`, entry.context);
      }

      if (entry.error) {
        console.error(`  Error:`, entry.error);
      }
    }

    // File output
    if (this.config.enableFile && this.logFile) {
      // Check if we need to rotate the log file
      const currentFileName = this.getLogFileName();
      if (this.currentLogFile !== join(this.config.logDir, currentFileName)) {
        await this.rotateLogFile();
      }

      const encoder = new TextEncoder();
      await this.logFile.write(encoder.encode(formatted));
    }
  }

  private shouldLog(level: LogLevel): boolean {
    return level >= this.config.level;
  }

  debug(message: string, context?: Record<string, unknown>): void {
    if (this.shouldLog(LogLevel.DEBUG)) {
      this.writeLog({
        timestamp: new Date().toISOString(),
        level: LogLevel.DEBUG,
        message,
        context,
      });
    }
  }

  info(message: string, context?: Record<string, unknown>): void {
    if (this.shouldLog(LogLevel.INFO)) {
      this.writeLog({
        timestamp: new Date().toISOString(),
        level: LogLevel.INFO,
        message,
        context,
      });
    }
  }

  warn(message: string, context?: Record<string, unknown>): void {
    if (this.shouldLog(LogLevel.WARN)) {
      this.writeLog({
        timestamp: new Date().toISOString(),
        level: LogLevel.WARN,
        message,
        context,
      });
    }
  }

  error(message: string, error?: Error, context?: Record<string, unknown>): void {
    if (this.shouldLog(LogLevel.ERROR)) {
      this.writeLog({
        timestamp: new Date().toISOString(),
        level: LogLevel.ERROR,
        message,
        error,
        context,
      });
    }
  }

  fatal(message: string, error?: Error, context?: Record<string, unknown>): void {
    if (this.shouldLog(LogLevel.FATAL)) {
      this.writeLog({
        timestamp: new Date().toISOString(),
        level: LogLevel.FATAL,
        message,
        error,
        context,
      });
    }
  }

  // Convenience methods for common operations
  startOperation(operation: string, context?: Record<string, unknown>): void {
    this.info(`🚀 Starting operation: ${operation}`, context);
  }

  endOperation(operation: string, context?: Record<string, unknown>): void {
    this.info(`✅ Completed operation: ${operation}`, context);
  }

  processingFile(filename: string, context?: Record<string, unknown>): void {
    this.debug(`📁 Processing file: ${filename}`, context);
  }

  fileProcessed(filename: string, result: string, context?: Record<string, unknown>): void {
    this.info(`✅ Processed file: ${filename} → ${result}`, context);
  }

  fileSkipped(filename: string, reason: string, context?: Record<string, unknown>): void {
    this.warn(`⏭️  Skipped file: ${filename} (${reason})`, context);
  }

  fileError(filename: string, error: Error, context?: Record<string, unknown>): void {
    this.error(`❌ Error processing file: ${filename}`, error, context);
  }

  duplicateFound(filename: string, originalFile: string, context?: Record<string, unknown>): void {
    this.warn(`🔄 Duplicate found: ${filename} (original: ${originalFile})`, context);
  }

  configurationLoaded(config: Record<string, string>, context?: Record<string, unknown>): void {
    this.debug("⚙️  Configuration loaded", { ...context, config });
  }

  configurationError(message: string, context?: Record<string, unknown>): void {
    this.error(`⚙️  Configuration error: ${message}`, undefined, context);
  }

  async close(): Promise<void> {
    if (this.logFile) {
      this.logFile.close();
    }
  }
}

// Global logger instance
let globalLogger: Logger | null = null;

export function getLogger(): Logger {
  if (!globalLogger) {
    // Initialize with default settings
    globalLogger = new Logger({
      level: LogLevel.INFO,
      enableConsole: true,
      enableFile: false,
    });
  }
  return globalLogger;
}

export function setLogger(logger: Logger): void {
  globalLogger = logger;
}

export function configureLogger(config: Partial<LoggerConfig>): void {
  const logger = new Logger(config);
  setLogger(logger);
}

// Convenience functions for quick logging
export function debug(message: string, context?: Record<string, unknown>): void {
  getLogger().debug(message, context);
}

export function info(message: string, context?: Record<string, unknown>): void {
  getLogger().info(message, context);
}

export function warn(message: string, context?: Record<string, unknown>): void {
  getLogger().warn(message, context);
}

export function error(message: string, error?: Error, context?: Record<string, unknown>): void {
  getLogger().error(message, error, context);
}

export function fatal(message: string, error?: Error, context?: Record<string, unknown>): void {
  getLogger().fatal(message, error, context);
}
