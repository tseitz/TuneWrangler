#!/usr/bin/env -S deno run --allow-read --allow-write --allow-run --allow-net --allow-env --allow-sys

import { parse } from "https://deno.land/std@0.224.0/flags/mod.ts";
import { validateConfiguration } from "../core/utils/common.ts";
import { logError } from "../core/utils/errors.ts";
import { configureLogger, getLogger, LogLevel } from "../core/utils/logger.ts";

// Import all commands
import {
  renameMusic,
  renameBandcamp,
  renameItunes,
  renameBeatport,
  addM3uToYoutube,
  playlistImport,
  convertFlacs,
  validate,
} from "./commands/validate.ts";
import { logs } from "./commands/logs.ts";

const VERSION = "1.0.0";

interface Command {
  name: string;
  description: string;
  usage: string;
  examples: string[];
  execute: (args: string[]) => Promise<void>;
}

const commands: Record<string, Command> = {
  "rename-music": {
    name: "rename-music",
    description: "Rename music files with proper artist - title format",
    usage: "tunewrangler rename-music [options]",
    examples: ["tunewrangler rename-music", "tunewrangler rename-music --help"],
    execute: renameMusic,
  },
  "rename-bandcamp": {
    name: "rename-bandcamp",
    description: "Rename Bandcamp music files",
    usage: "tunewrangler rename-bandcamp [options]",
    examples: ["tunewrangler rename-bandcamp", "tunewrangler rename-bandcamp --help"],
    execute: renameBandcamp,
  },
  "rename-itunes": {
    name: "rename-itunes",
    description: "Rename iTunes music files",
    usage: "tunewrangler rename-itunes [options]",
    examples: ["tunewrangler rename-itunes", "tunewrangler rename-itunes --help"],
    execute: renameItunes,
  },
  "rename-beatport": {
    name: "rename-beatport",
    description: "Rename Beatport music files",
    usage: "tunewrangler rename-beatport [options]",
    examples: ["tunewrangler rename-beatport", "tunewrangler rename-beatport --help"],
    execute: renameBeatport,
  },
  youtube: {
    name: "youtube",
    description: "Add M3U playlists to YouTube",
    usage: "tunewrangler youtube [options]",
    examples: ["tunewrangler youtube", "tunewrangler youtube --help"],
    execute: addM3uToYoutube,
  },
  playlist: {
    name: "playlist",
    description: "Import and process playlists",
    usage: "tunewrangler playlist [options]",
    examples: ["tunewrangler playlist", "tunewrangler playlist --help"],
    execute: playlistImport,
  },
  convert: {
    name: "convert",
    description: "Convert FLAC files to other formats",
    usage: "tunewrangler convert [options]",
    examples: ["tunewrangler convert", "tunewrangler convert --help"],
    execute: convertFlacs,
  },
  validate: {
    name: "validate",
    description: "Validate configuration and paths",
    usage: "tunewrangler validate [options]",
    examples: ["tunewrangler validate", "tunewrangler validate --help"],
    execute: validate,
  },
  logs: {
    name: "logs",
    description: "Manage and view log files",
    usage: "tunewrangler logs [options]",
    examples: ["tunewrangler logs --list", "tunewrangler logs --tail", "tunewrangler logs --help"],
    execute: logs,
  },
};

function showHelp(): void {
  console.log(`
🎵 TuneWrangler v${VERSION} - Music File Management Tool

USAGE:
  tunewrangler <command> [options]

COMMANDS:
${Object.values(commands)
  .map((cmd) => `  ${cmd.name.padEnd(20)} ${cmd.description}`)
  .join("\n")}

GLOBAL OPTIONS:
  --help, -h          Show help for a command
  --version, -v       Show version information
  --verbose           Enable verbose output
  --quiet             Suppress output

EXAMPLES:
  tunewrangler rename-music --help
  tunewrangler validate
  tunewrangler youtube --playlist my-playlist.m3u

For more information about a command, run:
  tunewrangler <command> --help
`);
}

function showVersion(): void {
  console.log(`TuneWrangler v${VERSION}`);
}

function showCommandHelp(commandName: string): void {
  const command = commands[commandName];
  if (!command) {
    console.error(`❌ Unknown command: ${commandName}`);
    console.log(`Run 'tunewrangler --help' to see available commands.`);
    Deno.exit(1);
  }

  console.log(`
🎵 TuneWrangler ${command.name}

${command.description}

USAGE:
  ${command.usage}

EXAMPLES:
${command.examples.map((example) => `  ${example}`).join("\n")}

Run 'tunewrangler --help' to see all available commands.
`);
}

async function main(): Promise<void> {
  const args = parse(Deno.args, {
    boolean: ["help", "version", "verbose", "quiet"],
    alias: {
      help: "h",
      version: "v",
    },
  }) as {
    help?: boolean;
    version?: boolean;
    verbose?: boolean;
    quiet?: boolean;
    _: string[];
  };

  // Configure logging based on CLI flags
  const logLevel = args.verbose ? LogLevel.DEBUG : args.quiet ? LogLevel.ERROR : LogLevel.INFO;
  configureLogger({
    level: logLevel,
    enableConsole: !args.quiet,
    enableFile: true,
    logDir: "./logs",
    format: "text",
  });

  const logger = getLogger();

  // Handle global flags
  if (args.help && args._.length === 0) {
    showHelp();
    return;
  }

  if (args.version) {
    showVersion();
    return;
  }

  logger.startOperation("TuneWrangler CLI", { args: args._ });

  // Get command and sub-args
  const commandName = args._[0] as string;
  const subArgs = args._.slice(1);

  // Show help for specific command
  if (args.help && commandName) {
    showCommandHelp(commandName);
    return;
  }

  // No command provided
  if (!commandName) {
    logger.error("No command specified");
    console.error("❌ No command specified");
    console.log("Run 'tunewrangler --help' to see available commands.");
    Deno.exit(1);
  }

  // Check if command exists
  const command = commands[commandName];
  if (!command) {
    logger.error(`Unknown command: ${commandName}`);
    console.error(`❌ Unknown command: ${commandName}`);
    console.log("Run 'tunewrangler --help' to see available commands.");
    Deno.exit(1);
  }

  // For logs command, pass all remaining arguments including flags
  if (commandName === "logs") {
    const logsArgs = Deno.args.slice(Deno.args.indexOf("logs") + 1);
    await command.execute(logsArgs);
    return;
  }

  // Validate configuration before running commands
  if (commandName !== "validate" && commandName !== "logs") {
    try {
      logger.debug("Validating configuration before running command");
      const isValid = await validateConfiguration();
      if (!isValid) {
        logger.error("Configuration validation failed");
        console.error("❌ Configuration validation failed. Run 'tunewrangler validate' to check your setup.");
        Deno.exit(1);
      }
      logger.debug("Configuration validation passed");
    } catch (error) {
      logger.error("Configuration validation error", error as Error, { operation: "configuration validation" });
      logError(error, { operation: "configuration validation" });
      Deno.exit(1);
    }
  }

  // Execute command
  try {
    logger.startOperation(command.name, { args: subArgs });
    console.log(`🚀 Running: ${command.name}`);
    await command.execute(subArgs);
    logger.endOperation(command.name, { success: true });
    console.log(`✅ ${command.name} completed successfully`);
  } catch (error) {
    logger.error(`Command execution failed: ${command.name}`, error as Error, { operation: command.name });
    logError(error, { operation: command.name });
    Deno.exit(1);
  }
}

// Run the CLI
if (import.meta.main) {
  main().catch(async (error) => {
    const logger = getLogger();
    logger.fatal("CLI execution failed", error as Error, { operation: "main" });
    logError(error, { operation: "main" });
    await logger.close();
    Deno.exit(1);
  });
}
