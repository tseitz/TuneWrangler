import { join } from "https://deno.land/std@0.224.0/path/mod.ts";
import { debug, warn, error } from "./logger.ts";

/**
 * Types of actions that can be performed in a flow step
 */
export type FlowStepType =
  | "click"
  | "fill"
  | "wait"
  | "waitForSelector"
  | "waitForPopup"
  | "switchToPopup"
  | "closePopup"
  | "waitForDownload"
  | "navigate"
  | "evaluate";

/**
 * A single step in a flow
 */
export interface FlowStep {
  /** Type of action to perform */
  type: FlowStepType;
  /** CSS selector or Playwright locator string */
  selector?: string;
  /** Value to fill (for fill actions), can use {{variable}} syntax */
  value?: string;
  /** Timeout for this step in ms */
  timeout?: number;
  /** Delay after action completes in ms */
  delay?: number;
  /** Human-readable description of what this step does */
  description?: string;
  /** If true, failure doesn't stop the flow */
  optional?: boolean;
  /** Number of retry attempts if step fails */
  retry?: number;
  /** JavaScript code to evaluate (for evaluate type) */
  code?: string;
  /** URL to navigate to (for navigate type) */
  url?: string;
}

/**
 * Metadata about a flow
 */
export interface FlowMetadata {
  /** Human-readable description of the flow */
  description?: string;
  /** Last update timestamp */
  lastUpdated?: string;
  /** Reference to original codegen output file */
  codegenSource?: string;
  /** Author of the flow */
  author?: string;
}

/**
 * A complete flow definition
 */
export interface Flow {
  /** Unique name for this flow */
  name: string;
  /** Platform this flow is for (hypeddit, toneden, soundcloud) */
  platform: string;
  /** URL patterns to match (e.g., ['hypeddit.com', 'hype.to']) */
  urlPatterns: string[];
  /** Steps to execute in order */
  steps: FlowStep[];
  /** Optional metadata */
  metadata?: FlowMetadata;
}

/**
 * Flow configuration file format
 */
export interface FlowConfig {
  /** Configuration version */
  version: string;
  /** Array of flows */
  flows: Flow[];
}

/**
 * Result of flow validation
 */
export interface FlowValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

/**
 * Flow configuration loader
 */
export class FlowConfigLoader {
  private flowsDir: string;
  private loadedConfigs: Map<string, FlowConfig> = new Map();

  constructor(flowsDir?: string) {
    // Default to src/config/flows relative to project root
    this.flowsDir = flowsDir || join(
      Deno.cwd(),
      "src",
      "config",
      "flows"
    );
  }

  /**
   * Load flow configuration for a platform
   */
  async loadFlowConfig(platform: string): Promise<FlowConfig | null> {
    // Check cache first
    if (this.loadedConfigs.has(platform)) {
      return this.loadedConfigs.get(platform)!;
    }

    const configPath = join(this.flowsDir, `${platform}.json`);

    try {
      const configText = await Deno.readTextFile(configPath);
      const config: FlowConfig = JSON.parse(configText);

      // Validate structure
      const validation = this.validateFlowConfig(config);
      if (!validation.valid) {
        error(`Invalid flow config for ${platform}`, undefined, {
          errors: validation.errors,
        });
        return null;
      }

      // Cache and return
      this.loadedConfigs.set(platform, config);
      debug(`Loaded flow config for ${platform}`, {
        flowCount: config.flows.length,
      });

      return config;
    } catch (err) {
      if ((err as Error).name === "NotFound") {
        debug(`No flow config found for ${platform}`, { path: configPath });
        return null;
      }
      error(`Failed to load flow config for ${platform}`, err as Error);
      return null;
    }
  }

  /**
   * Find a flow that matches the given URL
   */
  async findMatchingFlow(url: string): Promise<Flow | null> {
    try {
      const urlObj = new URL(url);
      const hostname = urlObj.hostname.toLowerCase();

      // Try to determine platform from URL
      let platform: string | null = null;
      if (hostname.includes("hypeddit") || hostname.includes("hype.to")) {
        platform = "hypeddit";
      } else if (hostname.includes("toneden")) {
        platform = "toneden";
      } else if (hostname.includes("soundcloud")) {
        platform = "soundcloud-track";
      }

      if (!platform) {
        debug("Could not determine platform from URL", { url, hostname });
        return null;
      }

      const config = await this.loadFlowConfig(platform);
      if (!config) {
        return null;
      }

      // Find flow matching URL patterns
      for (const flow of config.flows) {
        for (const pattern of flow.urlPatterns) {
          if (hostname.includes(pattern.toLowerCase())) {
            debug(`Found matching flow: ${flow.name}`, { url, pattern });
            return flow;
          }
        }
      }

      // If no specific match, return first flow for platform (fallback)
      if (config.flows.length > 0) {
        debug(`Using default flow for ${platform}`, {
          flowName: config.flows[0].name,
        });
        return config.flows[0];
      }

      return null;
    } catch (err) {
      warn("Error finding matching flow", { error: (err as Error).message, url });
      return null;
    }
  }

  /**
   * Validate a flow configuration structure
   */
  validateFlowConfig(config: FlowConfig): FlowValidationResult {
    const errors: string[] = [];
    const warnings: string[] = [];

    if (!config.version) {
      errors.push("Missing version field");
    }

    if (!config.flows || !Array.isArray(config.flows)) {
      errors.push("Missing or invalid flows array");
      return { valid: false, errors, warnings };
    }

    for (let i = 0; i < config.flows.length; i++) {
      const flow = config.flows[i];
      const flowValidation = this.validateFlow(flow);
      if (!flowValidation.valid) {
        errors.push(
          ...flowValidation.errors.map(
            (e) => `Flow ${i} (${flow.name}): ${e}`
          )
        );
      }
      if (flowValidation.warnings.length > 0) {
        warnings.push(
          ...flowValidation.warnings.map(
            (w) => `Flow ${i} (${flow.name}): ${w}`
          )
        );
      }
    }

    return {
      valid: errors.length === 0,
      errors,
      warnings,
    };
  }

  /**
   * Validate a single flow
   */
  validateFlow(flow: Flow): FlowValidationResult {
    const errors: string[] = [];
    const warnings: string[] = [];

    if (!flow.name) {
      errors.push("Flow missing name");
    }

    if (!flow.platform) {
      errors.push("Flow missing platform");
    }

    if (!flow.urlPatterns || !Array.isArray(flow.urlPatterns)) {
      errors.push("Flow missing or invalid urlPatterns");
    }

    if (!flow.steps || !Array.isArray(flow.steps)) {
      errors.push("Flow missing or invalid steps");
      return { valid: false, errors, warnings };
    }

    if (flow.steps.length === 0) {
      warnings.push("Flow has no steps");
    }

    // Validate each step
    for (let i = 0; i < flow.steps.length; i++) {
      const step = flow.steps[i];
      const stepErrors: string[] = [];

      if (!step.type) {
        stepErrors.push("Missing type");
      }

      // Validate step type-specific requirements
      if (step.type === "click" || step.type === "fill" || step.type === "waitForSelector") {
        if (!step.selector) {
          stepErrors.push("Missing selector");
        }
      }

      if (step.type === "fill" && !step.value) {
        stepErrors.push("Fill step missing value");
      }

      if (step.type === "navigate" && !step.url) {
        stepErrors.push("Navigate step missing url");
      }

      if (step.type === "evaluate" && !step.code) {
        stepErrors.push("Evaluate step missing code");
      }

      if (stepErrors.length > 0) {
        errors.push(`Step ${i}: ${stepErrors.join(", ")}`);
      }
    }

    return {
      valid: errors.length === 0,
      errors,
      warnings,
    };
  }

  /**
   * Clear the config cache (useful for testing or reloading)
   */
  clearCache(): void {
    this.loadedConfigs.clear();
  }
}

// Export singleton instance
export const flowConfigLoader = new FlowConfigLoader();
