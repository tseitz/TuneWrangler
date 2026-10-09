import { parseArgs } from "@std/cli/parse-args";
import { validateConfiguration } from "../../core/utils/common.ts";
import { loadConfig } from "../../config/index.ts";
import { getLogger } from "../../core/utils/logger.ts";

export async function renameMusic(args: string[]): Promise<void> {
  const flags = parseArgs(args, {
    boolean: ["help"],
    alias: { help: "h" },
  });

  if (flags.help) {
    console.log(`
🎵 TuneWrangler rename-music

Rename music files with proper artist - title format.

USAGE:
  tunewrangler rename-music [options]

OPTIONS:
  --help, -h    Show this help message

This command processes music files in the configured directories and renames them
to follow the standard "Artist - Title" format.
`);
    return;
  }

  // Import and run the actual processor
  await import("../../processors/renameMusic.ts");
}

export async function addM3uToYoutube(args: string[]): Promise<void> {
  const flags = parseArgs(args, {
    boolean: ["help"],
    string: ["playlist"],
    alias: { help: "h" },
  });

  if (flags.help) {
    console.log(`
🎵 TuneWrangler youtube

Add M3U playlists to YouTube.

USAGE:
  tunewrangler youtube [options]

OPTIONS:
  --help, -h              Show this help message
  --playlist <file>       Specify playlist file to process

This command adds M3U playlist files to YouTube playlists.
`);
    return;
  }

  // Import and run the actual processor
  await import("../../processors/addM3uToYoutubePlaylist.ts");
}

export async function playlistImport(args: string[]): Promise<void> {
  const flags = parseArgs(args, {
    boolean: ["help"],
    alias: { help: "h" },
  });

  if (flags.help) {
    console.log(`
🎵 TuneWrangler playlist

Import and process playlists.

USAGE:
  tunewrangler playlist [options]

OPTIONS:
  --help, -h    Show this help message

This command imports and processes playlist files.
`);
    return;
  }

  // Import and run the actual processor
  await import("../../processors/betterM3uSearch.ts");
}

export async function convertFlacs(args: string[]): Promise<void> {
  const flags = parseArgs(args, {
    boolean: ["help"],
    alias: { help: "h" },
  });

  if (flags.help) {
    console.log(`
🎵 TuneWrangler convert

Convert FLAC files to other formats.

USAGE:
  tunewrangler convert [options]

OPTIONS:
  --help, -h    Show this help message

This command converts FLAC files to other audio formats.
`);
    return;
  }

  // Import and run the actual processor
  await import("../../processors/convertFlacs.ts");
}

export async function validate(args: string[]): Promise<void> {
  const logger = getLogger();
  const flags = parseArgs(args, {
    boolean: ["help"],
    alias: { help: "h" },
  });

  if (flags.help) {
    console.log(`
🎵 TuneWrangler validate

Validate configuration and paths.

USAGE:
  tunewrangler validate [options]

OPTIONS:
  --help, -h    Show this help message

This command validates your TuneWrangler configuration and checks that all
configured paths exist and are accessible.
`);
    return;
  }

  logger.startOperation("validate configuration");
  console.log("🔧 Validating TuneWrangler configuration...\n");

  try {
    // Load and display configuration
    const config = loadConfig();
    logger.configurationLoaded(Object.fromEntries(Object.entries(config)));
    console.log("📋 Current Configuration:");
    Object.entries(config).forEach(([key, value]) => {
      console.log(`  ${key}: ${value}`);
    });
    console.log();

    // Validate configuration
    const isValid = await validateConfiguration();

    if (isValid) {
      logger.endOperation("validate configuration", { success: true });
      console.log("✅ Configuration is valid!");
    } else {
      logger.error("Configuration validation failed");
      console.log("❌ Configuration has issues. Please check the errors above.");
      Deno.exit(1);
    }
  } catch (error) {
    logger.error("Validation failed", error as Error);
    console.error("❌ Validation failed:", error);
    Deno.exit(1);
  }
}
