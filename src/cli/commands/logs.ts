import { parse } from "https://deno.land/std@0.224.0/flags/mod.ts";
import { join } from "https://deno.land/std@0.224.0/path/mod.ts";
import { getLogger } from "../../core/utils/logger.ts";

export async function logs(args: string[]): Promise<void> {
  const logger = getLogger();
  const flags = parse(args, {
    boolean: ["help", "list", "tail", "clear"],
    string: ["file"],
    alias: { help: "h" },
  });

  if (flags.help) {
    console.log(`
🎵 TuneWrangler logs

Manage and view log files.

USAGE:
  tunewrangler logs [options]

OPTIONS:
  --help, -h        Show this help message
  --list            List all log files
  --tail            Show the last 50 lines of the current log file
  --file <name>     Show contents of a specific log file
  --clear           Clear all log files

EXAMPLES:
  tunewrangler logs --list
  tunewrangler logs --tail
  tunewrangler logs --file tunewrangler-2025-07-18.log
  tunewrangler logs --clear
`);
    return;
  }

  logger.startOperation("logs command", { flags });

  try {
    if (flags.list) {
      await listLogFiles();
    } else if (flags.tail) {
      await tailLogFile();
    } else if (flags.file) {
      await showLogFile(flags.file);
    } else if (flags.clear) {
      await clearLogFiles();
    } else {
      // Default: list log files
      await listLogFiles();
    }

    logger.endOperation("logs command", { success: true });
  } catch (error) {
    logger.error("Logs command failed", error as Error);
    console.error("❌ Error:", error);
    Deno.exit(1);
  }
}

async function listLogFiles(): Promise<void> {
  const logDir = "./logs";

  try {
    const files: Array<{ name: string; size: number; modified: Date }> = [];

    for await (const entry of Deno.readDir(logDir)) {
      if (entry.isFile && entry.name.startsWith("tunewrangler-") && entry.name.endsWith(".log")) {
        const filePath = join(logDir, entry.name);
        const stat = await Deno.stat(filePath);
        files.push({
          name: entry.name,
          size: stat.size,
          modified: stat.mtime || new Date(),
        });
      }
    }

    // Sort by modification time (newest first)
    files.sort((a, b) => b.modified.getTime() - a.modified.getTime());

    console.log("📋 Log Files:");
    console.log("");

    if (files.length === 0) {
      console.log("  No log files found.");
      return;
    }

    for (const file of files) {
      const sizeKB = Math.round(file.size / 1024);
      const date = file.modified.toLocaleDateString();
      const time = file.modified.toLocaleTimeString();
      console.log(`  ${file.name} (${sizeKB}KB, ${date} ${time})`);
    }
  } catch (error) {
    if (error instanceof Deno.errors.NotFound) {
      console.log("📋 Log Files:");
      console.log("");
      console.log("  No log directory found.");
    } else {
      throw error;
    }
  }
}

async function showLogFile(fileName: string): Promise<void> {
  const logDir = "./logs";
  const filePath = join(logDir, fileName);

  try {
    const content = await Deno.readTextFile(filePath);
    console.log(`📄 Contents of ${fileName}:`);
    console.log("");

    if (content.trim() === "") {
      console.log("  (empty file)");
    } else {
      console.log(content);
    }
  } catch (error) {
    if (error instanceof Deno.errors.NotFound) {
      console.error(`❌ Log file not found: ${fileName}`);
    } else {
      throw error;
    }
  }
}

async function tailLogFile(): Promise<void> {
  const date = new Date().toISOString().split("T")[0];
  const fileName = `tunewrangler-${date}.log`;
  const logDir = "./logs";
  const filePath = join(logDir, fileName);

  try {
    const content = await Deno.readTextFile(filePath);
    const lines = content.split("\n").filter((line) => line.trim() !== "");
    const lastLines = lines.slice(-50);

    console.log(`📄 Last 50 lines of ${fileName}:`);
    console.log("");

    if (lastLines.length === 0) {
      console.log("  (empty file)");
    } else {
      console.log(lastLines.join("\n"));
    }
  } catch (error) {
    if (error instanceof Deno.errors.NotFound) {
      console.error(`❌ Log file not found: ${fileName}`);
    } else {
      throw error;
    }
  }
}

async function clearLogFiles(): Promise<void> {
  const logDir = "./logs";

  try {
    let count = 0;

    for await (const entry of Deno.readDir(logDir)) {
      if (entry.isFile && entry.name.startsWith("tunewrangler-") && entry.name.endsWith(".log")) {
        const filePath = join(logDir, entry.name);
        await Deno.remove(filePath);
        count++;
      }
    }

    console.log(`🗑️  Cleared ${count} log file(s).`);
  } catch (error) {
    if (error instanceof Deno.errors.NotFound) {
      console.log("🗑️  No log files to clear.");
    } else {
      throw error;
    }
  }
}
