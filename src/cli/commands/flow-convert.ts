import { parse } from "https://deno.land/std@0.224.0/flags/mod.ts";
import { join } from "https://deno.land/std@0.224.0/path/mod.ts";
import { ensureDir } from "https://deno.land/std@0.224.0/fs/mod.ts";
import { info, error, warn } from "../../core/utils/logger.ts";
import { Flow, FlowConfig, FlowStep } from "../../core/utils/flowConfig.ts";

/**
 * Convert Playwright codegen output to flow configuration
 */
export async function flowConvert(args: string[]): Promise<void> {
  const flags = parse(args, {
    boolean: ["help"],
    string: ["output", "platform", "name", "url-pattern"],
    alias: {
      help: "h",
      output: "o",
      platform: "p",
      name: "n",
      "url-pattern": "u",
    },
  });

  if (flags.help) {
    console.log(`
🔄 TuneWrangler flow-convert

Convert Playwright codegen output to flow configuration JSON.

USAGE:
  tunewrangler flow-convert <codegen-file> [options]

ARGUMENTS:
  <codegen-file>        Path to Playwright codegen output file (.ts or .js)

OPTIONS:
  --help, -h            Show this help message
  --output, -o <path>  Output path for flow JSON (default: src/config/flows/)
  --platform, -p <name> Platform name (hypeddit, toneden, soundcloud-track)
  --name, -n <name>     Flow name (default: extracted from codegen)
  --url-pattern, -u <pattern> URL pattern to match (can specify multiple)

EXAMPLES:
  # Convert codegen output to hypeddit flow
  tunewrangler flow-convert codegen-output.ts --platform hypeddit

  # Convert with custom name and URL patterns
  tunewrangler flow-convert my-flow.ts \\
    --platform toneden \\
    --name "ToneDen Standard Flow" \\
    --url-pattern "toneden.io" \\
    --url-pattern "toneden.com"

  # Convert to specific output file
  tunewrangler flow-convert codegen.ts --output flows/custom.json

HOW IT WORKS:
  1. Run Playwright codegen to capture interactions:
     npx playwright codegen https://hypeddit.com/track/...

  2. Save the generated code to a file

  3. Convert to flow configuration:
     tunewrangler flow-convert codegen-output.ts --platform hypeddit

  4. Refine selectors in the generated JSON file as needed
`);
    return;
  }

  const codegenFile = flags._[0] as string;
  if (!codegenFile) {
    error("Codegen file is required");
    console.error("❌ Codegen file is required");
    console.log("Run 'tunewrangler flow-convert --help' for usage information.");
    Deno.exit(1);
  }

  try {
    // Read codegen file
    const codegenContent = await Deno.readTextFile(codegenFile);
    info(`Reading codegen file: ${codegenFile}`);

    // Parse codegen output
    const steps = parseCodegenOutput(codegenContent);

    if (steps.length === 0) {
      warn("No steps found in codegen output");
      console.warn("⚠️  No steps found in codegen output");
      console.log("Make sure the file contains Playwright codegen output.");
      Deno.exit(1);
    }

    // Determine platform
    const platform = flags.platform || detectPlatform(codegenContent);
    if (!platform) {
      error("Could not determine platform");
      console.error("❌ Could not determine platform from codegen output");
      console.log("Please specify --platform (hypeddit, toneden, soundcloud-track)");
      Deno.exit(1);
    }

    // Determine flow name
    const flowName = flags.name || `Flow from ${codegenFile}`;

    // Get URL patterns
    const urlPatterns = flags["url-pattern"]
      ? (Array.isArray(flags["url-pattern"])
        ? flags["url-pattern"]
        : [flags["url-pattern"]])
      : detectUrlPatterns(codegenContent, platform);

    // Create flow
    const flow: Flow = {
      name: flowName,
      platform,
      urlPatterns,
      steps,
      metadata: {
        description: `Flow converted from ${codegenFile}`,
        lastUpdated: new Date().toISOString(),
        codegenSource: codegenFile,
      },
    };

    // Determine output path
    let outputPath: string;
    if (flags.output) {
      outputPath = flags.output;
    } else {
      const flowsDir = join(Deno.cwd(), "src", "config", "flows");
      await ensureDir(flowsDir);
      outputPath = join(flowsDir, `${platform}.json`);
    }

    // Load existing config or create new one
    let config: FlowConfig;
    try {
      const existingContent = await Deno.readTextFile(outputPath);
      config = JSON.parse(existingContent);
    } catch {
      // File doesn't exist, create new config
      config = {
        version: "1.0.0",
        flows: [],
      };
    }

    // Add or update flow
    const existingIndex = config.flows.findIndex((f) => f.name === flow.name);
    if (existingIndex >= 0) {
      info(`Updating existing flow: ${flow.name}`);
      config.flows[existingIndex] = flow;
    } else {
      info(`Adding new flow: ${flow.name}`);
      config.flows.push(flow);
    }

    // Write config
    await Deno.writeTextFile(
      outputPath,
      JSON.stringify(config, null, 2) + "\n"
    );

    info(`✅ Flow configuration saved to: ${outputPath}`);
    console.log(`\n✅ Flow configuration saved to: ${outputPath}`);
    console.log(`   Platform: ${platform}`);
    console.log(`   Flow name: ${flowName}`);
    console.log(`   Steps: ${steps.length}`);
    console.log(`   URL patterns: ${urlPatterns.join(", ")}`);
    console.log(
      `\n💡 You can now refine the selectors in the JSON file as needed.\n`
    );
  } catch (err) {
    error("Failed to convert codegen output", err as Error);
    console.error(`❌ Failed to convert codegen output: ${(err as Error).message}`);
    Deno.exit(1);
  }
}

/**
 * Parse Playwright codegen output and extract flow steps
 */
function parseCodegenOutput(content: string): FlowStep[] {
  const steps: FlowStep[] = [];
  const lines = content.split("\n");

  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();

    // Skip comments and empty lines
    if (!line || line.startsWith("//") || line.startsWith("/*")) {
      i++;
      continue;
    }

    // Parse page.click(selector)
    const clickMatch = line.match(/page\.click\(['"]([^'"]+)['"]\)/);
    if (clickMatch) {
      steps.push({
        type: "click",
        selector: clickMatch[1],
        description: `Click ${clickMatch[1]}`,
      });
      i++;
      continue;
    }

    // Parse page.fill(selector, value)
    const fillMatch = line.match(/page\.fill\(['"]([^'"]+)['"],\s*['"]([^'"]+)['"]\)/);
    if (fillMatch) {
      steps.push({
        type: "fill",
        selector: fillMatch[1],
        value: fillMatch[2],
        description: `Fill ${fillMatch[1]}`,
      });
      i++;
      continue;
    }

    // Parse page.waitForSelector(selector)
    const waitForSelectorMatch = line.match(/page\.waitForSelector\(['"]([^'"]+)['"]\)/);
    if (waitForSelectorMatch) {
      steps.push({
        type: "waitForSelector",
        selector: waitForSelectorMatch[1],
        description: `Wait for ${waitForSelectorMatch[1]}`,
      });
      i++;
      continue;
    }

    // Parse page.waitForEvent('popup')
    if (line.includes("waitForEvent") && line.includes("popup")) {
      steps.push({
        type: "waitForPopup",
        description: "Wait for popup to open",
      });
      i++;
      continue;
    }

    // Parse popup.click(selector) - add switchToPopup first
    const popupClickMatch = line.match(/popup\.click\(['"]([^'"]+)['"]\)/);
    if (popupClickMatch) {
      steps.push({
        type: "switchToPopup",
        description: "Switch to popup window",
      });
      steps.push({
        type: "click",
        selector: popupClickMatch[1],
        description: `Click ${popupClickMatch[1]} in popup`,
      });
      i++;
      continue;
    }

    // Parse popup.close()
    if (line.includes("popup.close()")) {
      steps.push({
        type: "closePopup",
        description: "Close popup window",
      });
      i++;
      continue;
    }

    // Parse await delay(ms)
    const delayMatch = line.match(/delay\((\d+)\)/);
    if (delayMatch) {
      steps.push({
        type: "wait",
        delay: parseInt(delayMatch[1], 10),
        description: `Wait ${delayMatch[1]}ms`,
      });
      i++;
      continue;
    }

    // Parse page.goto(url)
    const gotoMatch = line.match(/page\.goto\(['"]([^'"]+)['"]\)/);
    if (gotoMatch) {
      steps.push({
        type: "navigate",
        url: gotoMatch[1],
        description: `Navigate to ${gotoMatch[1]}`,
      });
      i++;
      continue;
    }

    // Parse page.waitForEvent('download')
    if (line.includes("waitForEvent") && line.includes("download")) {
      steps.push({
        type: "waitForDownload",
        description: "Wait for download",
      });
      i++;
      continue;
    }

    i++;
  }

  return steps;
}

/**
 * Detect platform from codegen content
 */
function detectPlatform(content: string): string | null {
  const lowerContent = content.toLowerCase();

  if (lowerContent.includes("hypeddit") || lowerContent.includes("hype.to")) {
    return "hypeddit";
  }
  if (lowerContent.includes("toneden")) {
    return "toneden";
  }
  if (lowerContent.includes("soundcloud")) {
    return "soundcloud-track";
  }

  return null;
}

/**
 * Detect URL patterns from codegen content
 */
function detectUrlPatterns(content: string, platform: string): string[] {
  const patterns: string[] = [];

  // Extract URLs from goto statements
  const urlMatches = content.matchAll(/goto\(['"](https?:\/\/[^'"]+)['"]\)/g);
  for (const match of urlMatches) {
    try {
      const url = new URL(match[1]);
      const hostname = url.hostname.replace(/^www\./, "");
      if (!patterns.includes(hostname)) {
        patterns.push(hostname);
      }
    } catch {
      // Invalid URL, skip
    }
  }

  // Add platform-specific defaults if no URLs found
  if (patterns.length === 0) {
    switch (platform) {
      case "hypeddit":
        patterns.push("hypeddit.com", "hype.to");
        break;
      case "toneden":
        patterns.push("toneden.io");
        break;
      case "soundcloud-track":
        patterns.push("soundcloud.com");
        break;
    }
  }

  return patterns;
}
