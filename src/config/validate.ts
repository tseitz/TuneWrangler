#!/usr/bin/env -S deno run --allow-env --allow-read

import { loadConfig, detectPlatform, validatePaths } from "./index.ts";

console.log("🔧 TuneWrangler Configuration Validator\n");

// Detect platform
const platform = detectPlatform();
console.log("📋 Platform Detection:");
console.log(`  OS: ${platform.isMac ? "macOS" : platform.isWindows ? "Windows" : "Linux"}`);
console.log(`  Home Directory: ${platform.homeDir}`);
console.log();

// Load configuration
console.log("⚙️  Configuration:");
const config = loadConfig();

for (const [key, path] of Object.entries(config)) {
  console.log(`  ${key}: ${path}`);
}
console.log();

// Validate paths
console.log("🔍 Validating Paths:");
const validation = await validatePaths(config);

if (validation.valid) {
  console.log("✅ All paths are valid!");
} else {
  console.log("❌ Some paths are invalid:");
  validation.errors.forEach((error) => console.log(`  - ${error}`));
}

console.log("\n💡 Environment Variables:");
console.log("You can override any path using environment variables:");
console.log("  TUNEWRANGLER_MUSIC_PATH=/custom/music/path");
console.log("  TUNEWRANGLER_DOWNLOADS_PATH=/custom/downloads/path");
console.log("  etc...");
