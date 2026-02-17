import { debug, info, warn, error } from "./logger.ts";
import { Flow, FlowStep } from "./flowConfig.ts";
import { GateCredentials } from "./soundcloudConfig.ts";
import { BrowserOptions } from "./hypedditGate.ts";
import { delay } from "./common.ts";
import { join } from "https://deno.land/std@0.224.0/path/mod.ts";

// deno-lint-ignore no-explicit-any
type Page = any;

/**
 * Context maintained during flow execution
 */
export interface FlowContext {
  /** Track opened popups */
  popups: Page[];
  /** Current active page */
  currentPage: Page;
  /** Credentials for variable substitution */
  credentials: GateCredentials;
  /** Variables for storing intermediate values */
  variables: Record<string, string>;
  /** Browser context (for popup handling) */
  // deno-lint-ignore no-explicit-any
  browserContext?: any;
}

/**
 * Result of executing a single step
 */
export interface StepResult {
  success: boolean;
  error?: string;
  /** Popup page if one was opened */
  popup?: Page;
  /** Download object if download was triggered */
  // deno-lint-ignore no-explicit-any
  download?: any;
}

/**
 * Result of executing a complete flow
 */
export interface FlowResult {
  success: boolean;
  /** URL of downloaded file */
  downloadUrl?: string;
  /** Path to downloaded file */
  downloadedFilePath?: string;
  /** Error message if flow failed */
  error?: string;
  /** Steps that were successfully executed */
  stepsCompleted: number;
  /** Total steps in flow */
  totalSteps: number;
}

/**
 * Flow executor that runs flow configurations
 */
export class FlowExecutor {
  /**
   * Execute a complete flow
   */
  async executeFlow(
    page: Page,
    flow: Flow,
    credentials: GateCredentials,
    options: BrowserOptions,
    // deno-lint-ignore no-explicit-any
    browserContext?: any
  ): Promise<FlowResult> {
    info(`🔄 Executing flow: ${flow.name}`, {
      platform: flow.platform,
      stepCount: flow.steps.length,
    });

    const context: FlowContext = {
      popups: [],
      currentPage: page,
      credentials,
      variables: {},
      browserContext,
    };

    let stepsCompleted = 0;
    const totalSteps = flow.steps.length;

    try {
      for (let i = 0; i < flow.steps.length; i++) {
        const step = flow.steps[i];
        const stepNum = i + 1;

        debug(`Executing step ${stepNum}/${totalSteps}: ${step.type}`, {
          description: step.description,
          selector: step.selector,
        });

        const stepResult = await this.executeStep(step, context, options);

        if (!stepResult.success) {
          if (step.optional) {
            warn(`Optional step ${stepNum} failed, continuing`, {
              error: stepResult.error,
            });
            continue;
          }

          // Retry logic
          if (step.retry && step.retry > 0) {
            let retried = false;
            for (let attempt = 0; attempt < step.retry; attempt++) {
              debug(`Retrying step ${stepNum}, attempt ${attempt + 1}/${step.retry}`);
              await delay(options.actionDelay);
              const retryResult = await this.executeStep(step, context, options);
              if (retryResult.success) {
                retried = true;
                break;
              }
            }
            if (!retried) {
              error(`Step ${stepNum} failed after retries`, undefined, {
                step: step.description || step.type,
                error: stepResult.error,
              });
              return {
                success: false,
                error: `Step ${stepNum} failed: ${stepResult.error}`,
                stepsCompleted,
                totalSteps,
              };
            }
          } else {
            error(`Step ${stepNum} failed`, undefined, {
              step: step.description || step.type,
              error: stepResult.error,
            });
            return {
              success: false,
              error: `Step ${stepNum} failed: ${stepResult.error}`,
              stepsCompleted,
              totalSteps,
            };
          }
        }

        stepsCompleted++;

        // Handle step-specific results
        if (stepResult.popup) {
          context.popups.push(stepResult.popup);
          context.currentPage = stepResult.popup;
        }

        if (stepResult.download) {
          // Download was triggered, save it
          const suggestedFilename = stepResult.download.suggestedFilename();
          const filePath = join(options.outputDir, suggestedFilename);
          await stepResult.download.saveAs(filePath);

          info(`✅ Flow completed successfully with download`, {
            filePath,
            stepsCompleted,
            totalSteps,
          });

          return {
            success: true,
            downloadedFilePath: filePath,
            stepsCompleted,
            totalSteps,
          };
        }

        // Apply delay after step
        if (step.delay) {
          await delay(step.delay);
        } else if (options.actionDelay) {
          await delay(options.actionDelay);
        }
      }

      // Flow completed but no download yet - check for download button/link
      const downloadResult = await this.checkForDownload(
        context.currentPage,
        options
      );

      if (downloadResult.success) {
        return {
          success: true,
          downloadUrl: downloadResult.url,
          downloadedFilePath: downloadResult.filePath,
          stepsCompleted,
          totalSteps,
        };
      }

      // Flow completed but no download found
      warn("Flow completed but no download was triggered");
      return {
        success: false,
        error: "Flow completed but no download was found",
        stepsCompleted,
        totalSteps,
      };
    } catch (err) {
      error("Flow execution error", err as Error);
      return {
        success: false,
        error: (err as Error).message,
        stepsCompleted,
        totalSteps,
      };
    }
  }

  /**
   * Execute a single flow step
   */
  private async executeStep(
    step: FlowStep,
    context: FlowContext,
    options: BrowserOptions
  ): Promise<StepResult> {
    const page = context.currentPage;
    const timeout = step.timeout || options.timeout || 30000;

    try {
      switch (step.type) {
        case "click": {
          if (!step.selector) {
            return { success: false, error: "Click step missing selector" };
          }

          const element = await page.$(step.selector);
          if (!element) {
            return {
              success: false,
              error: `Element not found: ${step.selector}`,
            };
          }

          const isVisible = await element.isVisible().catch(() => false);
          if (!isVisible) {
            return {
              success: false,
              error: `Element not visible: ${step.selector}`,
            };
          }

          await element.click({ timeout });
          return { success: true };
        }

        case "fill": {
          if (!step.selector) {
            return { success: false, error: "Fill step missing selector" };
          }
          if (!step.value) {
            return { success: false, error: "Fill step missing value" };
          }

          const substitutedValue = this.substituteVariables(
            step.value,
            context.credentials,
            context.variables
          );

          const element = await page.$(step.selector);
          if (!element) {
            return {
              success: false,
              error: `Element not found: ${step.selector}`,
            };
          }

          await element.fill(substitutedValue, { timeout });
          return { success: true };
        }

        case "wait": {
          const waitTime = step.delay || 1000;
          await delay(waitTime);
          return { success: true };
        }

        case "waitForSelector": {
          if (!step.selector) {
            return {
              success: false,
              error: "waitForSelector step missing selector",
            };
          }

          await page.waitForSelector(step.selector, { timeout });
          return { success: true };
        }

        case "waitForPopup": {
          if (!context.browserContext) {
            return {
              success: false,
              error: "Browser context required for popup handling",
            };
          }

          // Wait for popup to open
          try {
            const popup = await context.browserContext.waitForEvent("page", {
              timeout,
            });
            // Store popup for later use
            context.popups.push(popup);
            return { success: true, popup };
          } catch (err) {
            // Popup might already be open or timeout occurred
            // Check if there are any new pages
            const pages = context.browserContext.pages();
            if (pages.length > 1) {
              const popup = pages[pages.length - 1];
              context.popups.push(popup);
              return { success: true, popup };
            }
            return {
              success: false,
              error: "Popup did not open within timeout",
            };
          }
        }

        case "switchToPopup": {
          if (context.popups.length === 0) {
            // Try to get the latest popup from browser context
            if (context.browserContext) {
              const pages = context.browserContext.pages();
              if (pages.length > 1) {
                const popup = pages[pages.length - 1];
                context.popups.push(popup);
                context.currentPage = popup;
                return { success: true, popup };
              }
            }
            return { success: false, error: "No popup available" };
          }

          const popup = context.popups[context.popups.length - 1];
          context.currentPage = popup;
          return { success: true, popup };
        }

        case "closePopup": {
          if (context.popups.length === 0) {
            return { success: false, error: "No popup to close" };
          }

          const popup = context.popups.pop()!;
          await popup.close().catch(() => {});
          context.currentPage = context.browserContext
            ? context.browserContext.pages()[0]
            : page;
          return { success: true };
        }

        case "waitForDownload": {
          const downloadPromise = page.waitForEvent("download", { timeout });
          const download = await downloadPromise;
          return { success: true, download };
        }

        case "navigate": {
          if (!step.url) {
            return { success: false, error: "Navigate step missing url" };
          }

          const substitutedUrl = this.substituteVariables(
            step.url,
            context.credentials,
            context.variables
          );

          await page.goto(substitutedUrl, {
            waitUntil: "load",
            timeout,
          });
          return { success: true };
        }

        case "evaluate": {
          if (!step.code) {
            return { success: false, error: "Evaluate step missing code" };
          }

          const result = await page.evaluate(step.code);
          // Store result in variables if needed
          if (step.selector) {
            context.variables[step.selector] = String(result);
          }
          return { success: true };
        }

        default:
          return {
            success: false,
            error: `Unknown step type: ${(step as FlowStep).type}`,
          };
      }
    } catch (err) {
      return {
        success: false,
        error: (err as Error).message,
      };
    }
  }

  /**
   * Substitute variables in a string (e.g., {{credentials.email}})
   */
  private substituteVariables(
    value: string,
    credentials: GateCredentials,
    variables: Record<string, string>
  ): string {
    let result = value;

    // Replace credential variables
    result = result.replace(/\{\{credentials\.email\}\}/g, credentials.email || "");
    result = result.replace(
      /\{\{credentials\.soundcloudUsername\}\}/g,
      credentials.soundcloudUsername || ""
    );
    result = result.replace(
      /\{\{credentials\.defaultComment\}\}/g,
      credentials.defaultComment || ""
    );

    // Replace custom variables
    for (const [key, val] of Object.entries(variables)) {
      result = result.replace(new RegExp(`\\{\\{${key}\\}\\}`, "g"), val);
    }

    return result;
  }

  /**
   * Check for download button/link after flow completion
   */
  private async checkForDownload(
    page: Page,
    options: BrowserOptions
  ): Promise<{ success: boolean; url?: string; filePath?: string }> {
    try {
      // Set up download listener
      const downloadPromise = page.waitForEvent("download", {
        timeout: 5000,
      }).catch(() => null);

      // Look for download button
      const downloadSelectors = [
        'button:has-text("Download")',
        'button:has-text("DOWNLOAD")',
        'a:has-text("Download")',
        'a[download]',
        'a[href*="download"]',
      ];

      for (const selector of downloadSelectors) {
        try {
          const element = await page.$(selector);
          if (element) {
            const isVisible = await element.isVisible().catch(() => false);
            if (isVisible) {
              await element.click();
              const download = await downloadPromise;
              if (download) {
                const suggestedFilename = download.suggestedFilename();
                const filePath = join(options.outputDir, suggestedFilename);
                await download.saveAs(filePath);
                return { success: true, filePath };
              }
            }
          }
        } catch {
          // Continue to next selector
        }
      }

      return { success: false };
    } catch (err) {
      debug("Error checking for download", { error: (err as Error).message });
      return { success: false };
    }
  }
}

// Export singleton instance
export const flowExecutor = new FlowExecutor();
