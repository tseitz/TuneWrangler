import { join } from "https://deno.land/std@0.224.0/path/mod.ts";
import { ensureDir } from "https://deno.land/std@0.224.0/fs/mod.ts";
import { debug, info, warn, error } from "./logger.ts";
import { GateCredentials } from "./soundcloudConfig.ts";
import { delay, sanitizeFilename } from "./common.ts";
import { flowConfigLoader } from "./flowConfig.ts";
import { flowExecutor } from "./flowExecutor.ts";

/**
 * Browser automation constants
 */
const DEFAULT_BROWSER_ARGS = ["--no-sandbox", "--disable-setuid-sandbox"];
const DEFAULT_USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";
const DEFAULT_PAGE_STABILIZATION_DELAY = 2000;
const DEFAULT_POPUP_WAIT_TIMEOUT = 10000;
const DEFAULT_LOGIN_POLL_INTERVAL = 2000;
const DEFAULT_LOGIN_MAX_WAIT_TIME = 300000; // 5 minutes

// Playwright types - we'll use dynamic import for the actual module
// deno-lint-ignore no-explicit-any
type Browser = any;
// deno-lint-ignore no-explicit-any
type Page = any;
// deno-lint-ignore no-explicit-any
type BrowserContext = any;

/**
 * Types of actions that may be required by a download gate
 */
export enum GateAction {
  EMAIL = "email",
  SOUNDCLOUD_FOLLOW = "soundcloud_follow",
  SOUNDCLOUD_LIKE = "soundcloud_like",
  SOUNDCLOUD_REPOST = "soundcloud_repost",
  SPOTIFY_FOLLOW = "spotify_follow",
  YOUTUBE_SUBSCRIBE = "youtube_subscribe",
  COMMENT = "comment",
  UNKNOWN = "unknown",
}

/**
 * Detected required actions for a gate
 */
export interface RequiredActions {
  email: boolean;
  soundcloudFollow: boolean;
  soundcloudLike: boolean;
  soundcloudRepost: boolean;
  spotifyFollow: boolean;
  youtubeSubscribe: boolean;
  comment: boolean;
  other: string[];
}

/**
 * Result of gate bypass attempt
 */
export interface GateBypassResult {
  success: boolean;
  downloadUrl?: string;
  downloadedFilePath?: string;
  error?: string;
  skipped?: boolean;
  skipReason?: string;
  actionsCompleted?: GateAction[];
}

/**
 * Browser options for gate handling
 */
export interface BrowserOptions {
  /** Run browser in headless mode */
  headless: boolean;
  /** Timeout for operations in ms */
  timeout: number;
  /** Delay between actions in ms */
  actionDelay: number;
  /** Output directory for downloads */
  outputDir: string;
  /** Path to store browser session data (for persistent login) */
  sessionPath?: string;
  /** SoundCloud OAuth token (injected as cookie for authentication) */
  oauthToken?: string;
}

/**
 * Hypeddit and similar download gate handler using browser automation
 * 
 * This class handles automated interaction with download gate platforms (Hypeddit, ToneDen, etc.)
 * to complete required actions (email signup, follow, like, comment) and download tracks.
 * 
 * @example
 * ```typescript
 * const handler = new HypedditGateHandler();
 * await handler.initialize({ headless: true, timeout: 30000, actionDelay: 1000, outputDir: "./downloads" });
 * const result = await handler.bypassGate(gateUrl, credentials, options);
 * await handler.close();
 * ```
 */
export class HypedditGateHandler {
  private browser: Browser | null = null;
  private context: BrowserContext | null = null;
  // deno-lint-ignore no-explicit-any
  private playwright: any = null;

  /**
   * Initialize the browser automation
   * 
   * Sets up Playwright browser instance with persistent session support for login persistence.
   * Must be called before using other methods.
   * 
   * @param options - Browser configuration options
   * @throws Error if Playwright is not installed or browser initialization fails
   */
  async initialize(options: BrowserOptions): Promise<void> {
    if (this.browser) {
      return; // Already initialized
    }

    info("🌐 Initializing browser for gate handling", {
      headless: options.headless,
      persistentSession: !!options.sessionPath,
    });

    try {
      // Dynamic import of playwright
      // Note: User needs to install playwright: npx playwright install chromium
      this.playwright = await import("npm:playwright");

      // Set download path
      const downloadPath = join(options.outputDir, ".downloads");
      await ensureDir(downloadPath);

      // Use persistent context if session path is provided
      // This saves cookies, localStorage, etc. between runs
      if (options.sessionPath) {
        await ensureDir(options.sessionPath);
        info("🔐 Using persistent browser session", { path: options.sessionPath });
        
        // launchPersistentContext creates a browser with saved state
        this.context = await this.playwright.chromium.launchPersistentContext(
          options.sessionPath,
          {
            headless: options.headless,
            args: DEFAULT_BROWSER_ARGS,
            userAgent: DEFAULT_USER_AGENT,
            acceptDownloads: true,
          }
        );
        // In persistent context, browser is managed internally
        this.browser = { close: async () => {} }; // Stub - context handles cleanup
      } else {
        this.browser = await this.playwright.chromium.launch({
          headless: options.headless,
          args: DEFAULT_BROWSER_ARGS,
        });

        this.context = await this.browser.newContext({
          userAgent: DEFAULT_USER_AGENT,
          acceptDownloads: true,
        });
      }

      // Inject SoundCloud OAuth token as cookie if provided
      if (options.oauthToken && this.context) {
        info("🔐 Injecting SoundCloud OAuth token...");
        await this.context.addCookies([
          {
            name: "oauth_token",
            value: options.oauthToken,
            domain: ".soundcloud.com",
            path: "/",
            httpOnly: false,
            secure: true,
            sameSite: "Lax" as const,
          },
        ]);
        debug("OAuth token cookie injected");
      }

      debug("Browser initialized successfully");
    } catch (err) {
      error("Failed to initialize browser", err as Error);
      throw new Error(
        `Failed to initialize browser automation. Make sure Playwright is installed: npx playwright install chromium\n${
          (err as Error).message
        }`
      );
    }
  }

  /**
   * Open SoundCloud login page and wait for user to log in
   * 
   * This saves the session for future use. If a persistent session path is provided,
   * the login state will be saved and reused in subsequent runs.
   * 
   * @param options - Browser configuration options (should have sessionPath for persistence)
   * @returns true if login was successful, false if timed out or cancelled
   * @throws Error if browser initialization fails
   */
  async loginToSoundCloud(options: BrowserOptions): Promise<boolean> {
    await this.initialize(options);
    
    if (!this.context) {
      throw new Error("Browser not initialized");
    }

    info("🔐 Opening SoundCloud login page...");
    
    const page = await this.context.newPage();
    
    try {
      // First, check if we're already logged in by going to SoundCloud
      await page.goto("https://soundcloud.com", { waitUntil: "load", timeout: 30000 });
      await delay(DEFAULT_PAGE_STABILIZATION_DELAY);
      
      // Check for login indicator (user avatar or profile link)
      const isLoggedIn = await page.evaluate(`
        (() => {
          // Look for user menu / avatar which indicates logged in
          const userMenu = document.querySelector('.header__userNavUsernameButton, .header__userNav, [class*="userNav"]');
          const loginButton = document.querySelector('button[title="Sign in"], a[href*="signin"]');
          return !!userMenu && !loginButton;
        })()
      `);
      
      if (isLoggedIn) {
        info("✅ Already logged in to SoundCloud! Session is valid.");
        console.log("\n✅ You're already logged in to SoundCloud!");
        console.log("   Your session is saved and ready to use.\n");
        return true;
      }
      
      // Not logged in, go to signin page
      console.log("\n" + "=".repeat(60));
      console.log("📱 Please log in to SoundCloud in the browser window.");
      console.log("   Your session will be saved for future runs.");
      console.log("   ");
      console.log("   Waiting up to 5 minutes for login...");
      console.log("   (Press Ctrl+C to cancel)");
      console.log("=".repeat(60) + "\n");
      
      await page.goto("https://soundcloud.com/signin", { waitUntil: "load", timeout: 30000 });
      
      // Poll for login completion (check every 2 seconds for up to 5 minutes)
      const startTime = Date.now();
      
      while (Date.now() - startTime < DEFAULT_LOGIN_MAX_WAIT_TIME) {
        await delay(DEFAULT_LOGIN_POLL_INTERVAL);
        
        const currentUrl = page.url();
        
        // Check if we've navigated away from signin
        if (!currentUrl.includes("/signin") && !currentUrl.includes("/connect")) {
          // Verify we're actually logged in
          const loggedInNow = await page.evaluate(`
            (() => {
              const userMenu = document.querySelector('.header__userNavUsernameButton, .header__userNav, [class*="userNav"]');
              return !!userMenu;
            })()
          `).catch(() => false);
          
          if (loggedInNow || !currentUrl.includes("soundcloud.com/signin")) {
            info("✅ SoundCloud login successful! Session saved.");
            console.log("\n✅ Login successful! Session saved for future runs.\n");
            return true;
          }
        }
        
        // Check if browser was closed
        if (page.isClosed()) {
          warn("Browser was closed before login completed");
          return false;
        }
      }
      
      warn("⚠️ Login timed out after 5 minutes");
      return false;
    } catch (err) {
      // Browser might have been closed
      if ((err as Error).message.includes("closed") || (err as Error).message.includes("Target closed")) {
        info("Browser was closed");
        return false;
      }
      throw err;
    } finally {
      if (!page.isClosed()) {
        await page.close().catch(() => {});
      }
    }
  }

  /**
   * Close the browser and cleanup resources
   * 
   * Should be called when done with the handler to free up resources.
   * Safe to call multiple times.
   */
  async close(): Promise<void> {
    if (this.context) {
      await this.context.close();
      this.context = null;
    }
    if (this.browser) {
      await this.browser.close();
      this.browser = null;
    }
    debug("Browser closed");
  }

  /**
   * Attempt to bypass a download gate and get the download
   * 
   * Automatically detects the gate platform (Hypeddit, ToneDen, etc.) and handles
   * the required actions (email, follow, like, comment) to unlock the download.
   * 
   * @param gateUrl - URL of the download gate page
   * @param credentials - Credentials for completing gate requirements
   * @param options - Browser configuration options
   * @returns Result object with success status, download URL/file path, and completed actions
   */
  async bypassGate(
    gateUrl: string,
    credentials: GateCredentials,
    options: BrowserOptions
  ): Promise<GateBypassResult> {
    info(`🔓 Attempting to bypass gate: ${gateUrl}`);

    if (!this.browser) {
      await this.initialize(options);
    }

    const page: Page = await this.context!.newPage();
    const actionsCompleted: GateAction[] = [];

    try {
      // Set timeout
      page.setDefaultTimeout(options.timeout);

      // Navigate to the gate page - use "load" instead of "networkidle" to avoid timeouts
      // on pages that keep making background requests
      await page.goto(gateUrl, { waitUntil: "load", timeout: options.timeout });
      
      // Wait for page to stabilize
      await delay(options.actionDelay * 2);

      // Try to find and execute a flow first
      const flow = await flowConfigLoader.findMatchingFlow(gateUrl);
      if (flow) {
        info(`📋 Using flow: ${flow.name}`, { platform: flow.platform });
        
        const flowResult = await flowExecutor.executeFlow(
          page,
          flow,
          credentials,
          options,
          this.context
        );

        if (flowResult.success) {
          // Map flow completion to actions (simplified - flows handle this internally)
          if (flowResult.downloadedFilePath || flowResult.downloadUrl) {
            return {
              success: true,
              downloadUrl: flowResult.downloadUrl,
              downloadedFilePath: flowResult.downloadedFilePath,
              actionsCompleted, // Flows handle actions internally
            };
          }
        } else {
          warn(`Flow execution failed, falling back to hardcoded logic`, {
            error: flowResult.error,
          });
        }
      }

      // Fallback to hardcoded logic if no flow found or flow failed
      info("Using hardcoded gate handling (fallback)");

      // Detect which gate platform we're on
      const gatePlatform = await this.detectGatePlatform(page);
      info(`🔍 Detected gate platform: ${gatePlatform}`);

      // Handle platform-specific flows
      if (gatePlatform === "toneden") {
        return await this.handleTonedenGate(page, credentials, options, actionsCompleted);
      } else if (gatePlatform === "hypeddit") {
        return await this.handleHypedditGate(page, credentials, options, actionsCompleted);
      }
      
      // Generic gate handling for unknown platforms
      info("Using generic gate handling...");

      // Detect what actions are required
      const requiredActions = await this.detectRequiredActions(page);
      debug("Detected required actions", { requiredActions });

      // Check if we can complete the required actions
      const canComplete = this.canCompleteActions(requiredActions, credentials);
      if (!canComplete.can) {
        return {
          success: false,
          skipped: true,
          skipReason: `Missing credentials for required actions: ${canComplete.missing.join(", ")}`,
        };
      }

      // Complete each required action
      if (requiredActions.email && credentials.email) {
        await this.submitEmail(page, credentials.email, options.actionDelay);
        actionsCompleted.push(GateAction.EMAIL);
      }

      if (requiredActions.comment && credentials.defaultComment) {
        await this.submitComment(page, credentials.defaultComment, options.actionDelay);
        actionsCompleted.push(GateAction.COMMENT);
      }

      // SoundCloud actions require being logged in, which we handle differently
      if (requiredActions.soundcloudFollow) {
        const followed = await this.handleSoundCloudFollow(page, options.actionDelay);
        if (followed) {
          actionsCompleted.push(GateAction.SOUNDCLOUD_FOLLOW);
        }
      }

      if (requiredActions.soundcloudLike) {
        const liked = await this.handleSoundCloudLike(page, options.actionDelay);
        if (liked) {
          actionsCompleted.push(GateAction.SOUNDCLOUD_LIKE);
        }
      }

      if (requiredActions.soundcloudRepost) {
        const reposted = await this.handleSoundCloudRepost(page, options.actionDelay);
        if (reposted) {
          actionsCompleted.push(GateAction.SOUNDCLOUD_REPOST);
        }
      }

      // Wait for any animations/transitions
      await delay(options.actionDelay);

      // Try to find and click the download button
      const downloadResult = await this.getDownload(page, options);

      if (downloadResult.success) {
        info(`✅ Gate bypassed successfully`);
        return {
          success: true,
          downloadUrl: downloadResult.url,
          downloadedFilePath: downloadResult.filePath,
          actionsCompleted,
        };
      } else {
        return {
          success: false,
          error: downloadResult.error || "Could not complete download",
          actionsCompleted,
        };
      }
    } catch (err) {
      error(`Gate bypass failed: ${gateUrl}`, err as Error);
      return {
        success: false,
        error: (err as Error).message,
        actionsCompleted,
      };
    } finally {
      await page.close();
    }
  }

  /**
   * Detect which gate platform we're on
   * 
   * @param page - Playwright page object
   * @returns Platform name ("hypeddit", "toneden", "fanlink", or "unknown")
   */
  private async detectGatePlatform(page: Page): Promise<string> {
    const url = page.url();
    
    if (url.includes("toneden.io")) {
      return "toneden";
    }
    if (url.includes("hypeddit.com") || url.includes("hype.to")) {
      return "hypeddit";
    }
    if (url.includes("fanlink.to")) {
      return "fanlink";
    }
    
    // Try to detect from page content
    const content = await page.content();
    if (content.includes("toneden") || content.includes("ToneDen")) {
      return "toneden";
    }
    if (content.includes("hypeddit") || content.includes("Hypeddit")) {
      return "hypeddit";
    }
    
    return "unknown";
  }

  /**
   * Handle ToneDen gate specifically
   * 
   * ToneDen gates typically require completing social media actions (follow, like, subscribe)
   * before the download is unlocked. This method handles the ToneDen-specific flow.
   * 
   * @param page - Playwright page object
   * @param credentials - Credentials for completing gate requirements
   * @param options - Browser configuration options
   * @param actionsCompleted - Array to track completed actions
   * @returns Result object with success status and download information
   */
  private async handleTonedenGate(
    page: Page,
    credentials: GateCredentials,
    options: BrowserOptions,
    actionsCompleted: GateAction[]
  ): Promise<GateBypassResult> {
    info("🎵 Processing ToneDen gate...");
    
    try {
      // Wait for page to stabilize
      await delay(3000);
      
      // First, check if there's an initial "Download" or "Get" button we need to click
      // to reveal the action requirements
      info("🔍 Looking for initial download/unlock button...");
      const initialButtons = [
        'button:has-text("DOWNLOAD")',
        'button:has-text("Download")',
        'button:has-text("GET")',
        'button:has-text("Get")',
        'button:has-text("UNLOCK")',
        'a:has-text("DOWNLOAD")',
      ];
      
      for (const selector of initialButtons) {
        try {
          const btn = await page.$(selector);
          if (btn) {
            const isVisible = await btn.isVisible().catch(() => false);
            if (isVisible) {
              const text = await btn.textContent().catch(() => "");
              info(`📥 Found initial button: "${text?.trim()}"`);
              // Don't click yet - check if it's locked or requires actions
              break;
            }
          }
        } catch {
          // Continue
        }
      }
      
      // ToneDen gates typically require completing actions before download is unlocked
      // Common actions: Follow on SoundCloud, Follow on Spotify, Subscribe on YouTube, etc.
      
      // Look for action buttons using Playwright's more powerful locators
      info("🔍 Looking for required actions...");
      
      // Use getByRole and getByText for more reliable button finding
      const actionTexts = [
        'FOLLOW ON SOUNDCLOUD',
        'Follow on SoundCloud', 
        'FOLLOW ON SPOTIFY',
        'Follow on Spotify',
        'SUBSCRIBE',
        'LIKE',
      ];
      
      // First, let's see what buttons are available on the page
      const availableButtons = await page.evaluate(`
        (() => {
          const buttons = [];
          document.querySelectorAll('button, a, [role="button"], [class*="action"], [class*="btn"]').forEach(el => {
            const text = (el.textContent || '').trim();
            if (text && text.length < 100) {
              buttons.push({ tag: el.tagName, text: text.substring(0, 50), visible: el.offsetParent !== null });
            }
          });
          return buttons.filter(b => b.visible).slice(0, 20);
        })()
      `);
      debug("Available buttons on page:", { buttons: availableButtons });
      
      // Click action buttons that match our patterns
      for (const actionText of actionTexts) {
        try {
          // Use Playwright's locator with text matching
          const locator = page.locator(`button, a, [role="button"]`).filter({ hasText: new RegExp(actionText, 'i') });
          const count = await locator.count();
          
          if (count > 0) {
            for (let i = 0; i < count; i++) {
              const button = locator.nth(i);
              const isVisible = await button.isVisible().catch(() => false);
              if (isVisible) {
                const text = await button.textContent().catch(() => "");
                info(`🔘 Clicking action button: "${text?.trim()}"`);
                
                // Set up popup listener BEFORE clicking
                const popupPromise = this.context!.waitForEvent('page', { timeout: DEFAULT_POPUP_WAIT_TIMEOUT }).catch(() => null);
                
                await button.click();
                actionsCompleted.push(GateAction.SOUNDCLOUD_FOLLOW);
                
                // Wait for popup to open
                const popup = await popupPromise;
                
                if (popup) {
                  info("📱 Handling SoundCloud authorization popup...");
                  
                  try {
                    // Wait for popup to load
                    await popup.waitForLoadState('load', { timeout: 15000 }).catch(() => {});
                    await delay(2000);
                    
                    const popupUrl = popup.url();
                    info(`📱 Popup URL: ${popupUrl}`);
                    
                    // Check if it's a SoundCloud auth page
                    if (popupUrl.includes('soundcloud.com')) {
                      // Look for "Connect" or "Allow" button to approve the connection
                      const connectSelectors = [
                        'button:has-text("Connect")',
                        'button:has-text("Allow")',
                        'button:has-text("Authorize")',
                        'input[type="submit"][value*="Connect"]',
                        'input[type="submit"][value*="Allow"]',
                        'button[type="submit"]',
                        '.connect-button',
                        '#authorize-btn',
                      ];
                      
                      for (const connectSelector of connectSelectors) {
                        try {
                          const connectBtn = await popup.$(connectSelector);
                          if (connectBtn) {
                            const btnVisible = await connectBtn.isVisible().catch(() => false);
                            if (btnVisible) {
                              info("🔗 Clicking Connect/Allow button...");
                              await connectBtn.click();
                              await delay(3000);
                              break;
                            }
                          }
                        } catch {
                          // Continue to next selector
                        }
                      }
                    }
                    
                    // Wait for popup to close (either auto-close or after our click)
                    await popup.waitForEvent('close', { timeout: DEFAULT_POPUP_WAIT_TIMEOUT }).catch(() => {});
                    
                  } catch (popupErr) {
                    debug(`Popup handling error: ${(popupErr as Error).message}`);
                  } finally {
                    // Make sure popup is closed
                    if (!popup.isClosed()) {
                      await popup.close().catch(() => {});
                    }
                  }
                }
                
                // Wait a bit for ToneDen to register the action
                await delay(2000);
              }
            }
          }
        } catch {
          // Continue to next action text
        }
      }
      
      // Wait for unlock progress to complete
      await delay(2000);
      
      // Check if there's an email form
      const emailInput = await page.$('input[type="email"], input[name="email"], input[placeholder*="email" i]');
      if (emailInput && credentials.email) {
        info("📧 Submitting email...");
        await emailInput.fill(credentials.email);
        actionsCompleted.push(GateAction.EMAIL);
        await delay(500);
        
        // Find and click submit
        const submitBtn = await page.$(
          'button[type="submit"], button:has-text("Submit"), button:has-text("Continue")'
        );
        if (submitBtn) {
          await submitBtn.click();
          await delay(options.actionDelay * 2);
        }
      }
      
      // Now try to get the download - wait for DOWNLOAD button to appear/become enabled
      info("⏳ Waiting for download button to unlock...");
      
      // ToneDen download button selectors
      const downloadButtonSelectors = [
        'button:has-text("DOWNLOAD")',
        'button:has-text("Download")',
        'a:has-text("DOWNLOAD")',
        'a:has-text("Download")',
        '[class*="download"]:not([disabled])',
        'button[class*="download"]',
        'a[class*="download"]',
      ];
      
      // Wait up to 10 seconds for download button to become available
      let downloadButton = null;
      for (let attempt = 0; attempt < 10; attempt++) {
        for (const selector of downloadButtonSelectors) {
          try {
            const button = await page.$(selector);
            if (button) {
              const isVisible = await button.isVisible().catch(() => false);
              const isDisabled = await button.getAttribute("disabled").catch(() => null);
              const classes = await button.getAttribute("class").catch(() => "");
              
              // Check if button is visible and not disabled/locked
              if (isVisible && !isDisabled && !classes?.includes("locked") && !classes?.includes("disabled")) {
                downloadButton = button;
                break;
              }
            }
          } catch {
            // Continue
          }
        }
        
        if (downloadButton) {
          break;
        }
        
        await delay(1000);
      }
      
      // Set up download handling
      const downloadPromise = page.waitForEvent("download", { timeout: 30000 }).catch(() => null);
      
      if (downloadButton) {
        info("📥 Clicking download button...");
        await downloadButton.click();
        await delay(2000);
      }
      
      // Also check for direct download links
      const downloadLink = await page.$('a[download], a[href*=".mp3"], a[href*=".wav"], a[href*="download"]');
      if (downloadLink) {
        const href = await downloadLink.getAttribute("href");
        if (href) {
          info(`Found direct download link: ${href.substring(0, 50)}...`);
          
          // If it's a direct link, download it
          if (href.startsWith("http")) {
            return {
              success: true,
              downloadUrl: href,
              actionsCompleted,
            };
          }
        }
      }
      
      // Wait for download event
      const download = await downloadPromise;
      if (download) {
        const suggestedFilename = download.suggestedFilename();
        const filePath = `${options.outputDir}/${suggestedFilename}`;
        await download.saveAs(filePath);
        
        return {
          success: true,
          downloadedFilePath: filePath,
          actionsCompleted,
        };
      }
      
      // If we're in headed mode, give user time to interact
      if (!options.headless) {
        info("⏳ Waiting for manual interaction (headed mode)...");
        console.log("\n👆 Please complete any remaining actions in the browser.");
        console.log("   Click the DOWNLOAD button when it's unlocked.");
        console.log("   Waiting up to 60 seconds...\n");
        
        // Wait longer for user interaction
        const manualDownload = await page.waitForEvent("download", { timeout: 60000 }).catch(() => null);
        if (manualDownload) {
          const suggestedFilename = manualDownload.suggestedFilename();
          const filePath = `${options.outputDir}/${suggestedFilename}`;
          await manualDownload.saveAs(filePath);
          
          return {
            success: true,
            downloadedFilePath: filePath,
            actionsCompleted,
          };
        }
      }
      
      return {
        success: false,
        error: "Could not find download button or complete gate requirements",
        actionsCompleted,
      };
    } catch (err) {
      return {
        success: false,
        error: `ToneDen gate error: ${(err as Error).message}`,
        actionsCompleted,
      };
    }
  }

  /**
   * Handle Hypeddit gate specifically
   * 
   * Hypeddit gates typically require email signup, SoundCloud actions (follow, like, repost),
   * and sometimes comments. This method handles the Hypeddit-specific flow.
   * 
   * @param page - Playwright page object
   * @param credentials - Credentials for completing gate requirements
   * @param options - Browser configuration options
   * @param actionsCompleted - Array to track completed actions
   * @returns Result object with success status and download information
   */
  private async handleHypedditGate(
    page: Page,
    credentials: GateCredentials,
    options: BrowserOptions,
    actionsCompleted: GateAction[]
  ): Promise<GateBypassResult> {
    info("🎵 Processing Hypeddit gate...");
    
    // Use the existing generic flow which was designed for Hypeddit
    const requiredActions = await this.detectRequiredActions(page);
    debug("Detected required actions", { requiredActions });

    const canComplete = this.canCompleteActions(requiredActions, credentials);
    if (!canComplete.can) {
      return {
        success: false,
        skipped: true,
        skipReason: `Missing credentials for required actions: ${canComplete.missing.join(", ")}`,
      };
    }

    // Complete each required action
    if (requiredActions.email && credentials.email) {
      await this.submitEmail(page, credentials.email, options.actionDelay);
      actionsCompleted.push(GateAction.EMAIL);
    }

    if (requiredActions.comment && credentials.defaultComment) {
      await this.submitComment(page, credentials.defaultComment, options.actionDelay);
      actionsCompleted.push(GateAction.COMMENT);
    }

    if (requiredActions.soundcloudFollow) {
      const followed = await this.handleSoundCloudFollow(page, options.actionDelay);
      if (followed) {
        actionsCompleted.push(GateAction.SOUNDCLOUD_FOLLOW);
      }
    }

    if (requiredActions.soundcloudLike) {
      const liked = await this.handleSoundCloudLike(page, options.actionDelay);
      if (liked) {
        actionsCompleted.push(GateAction.SOUNDCLOUD_LIKE);
      }
    }

    if (requiredActions.soundcloudRepost) {
      const reposted = await this.handleSoundCloudRepost(page, options.actionDelay);
      if (reposted) {
        actionsCompleted.push(GateAction.SOUNDCLOUD_REPOST);
      }
    }

    await delay(options.actionDelay);

    const downloadResult = await this.getDownload(page, options);

    if (downloadResult.success) {
      return {
        success: true,
        downloadUrl: downloadResult.url,
        downloadedFilePath: downloadResult.filePath,
        actionsCompleted,
      };
    }
    
    // If in headed mode, give user time
    if (!options.headless) {
      info("⏳ Waiting for manual interaction (headed mode)...");
      console.log("\n👆 Please complete any remaining actions in the browser.");
      
      const manualDownload = await page.waitForEvent("download", { timeout: 60000 }).catch(() => null);
      if (manualDownload) {
        const suggestedFilename = manualDownload.suggestedFilename();
        const filePath = `${options.outputDir}/${suggestedFilename}`;
        await manualDownload.saveAs(filePath);
        
        return {
          success: true,
          downloadedFilePath: filePath,
          actionsCompleted,
        };
      }
    }

    return {
      success: false,
      error: downloadResult.error || "Could not complete download",
      actionsCompleted,
    };
  }

  /**
   * Detect what actions are required by the gate
   */
  private async detectRequiredActions(page: Page): Promise<RequiredActions> {
    const actions: RequiredActions = {
      email: false,
      soundcloudFollow: false,
      soundcloudLike: false,
      soundcloudRepost: false,
      spotifyFollow: false,
      youtubeSubscribe: false,
      comment: false,
      other: [],
    };

    try {
      // Check for email input
      const emailInput = await page.$('input[type="email"], input[name="email"], input[placeholder*="email" i]');
      actions.email = !!emailInput;

      // Check for SoundCloud actions (common Hypeddit patterns)
      const pageContent = await page.content();
      const contentLower = pageContent.toLowerCase();

      actions.soundcloudFollow =
        contentLower.includes("follow on soundcloud") ||
        contentLower.includes("soundcloud-follow") ||
        (await page.$('[data-action="soundcloud-follow"], .soundcloud-follow')) !== null;

      actions.soundcloudLike =
        contentLower.includes("like on soundcloud") ||
        contentLower.includes("soundcloud-like") ||
        (await page.$('[data-action="soundcloud-like"], .soundcloud-like')) !== null;

      actions.soundcloudRepost =
        contentLower.includes("repost on soundcloud") ||
        contentLower.includes("soundcloud-repost") ||
        (await page.$('[data-action="soundcloud-repost"], .soundcloud-repost')) !== null;

      // Check for Spotify
      actions.spotifyFollow =
        contentLower.includes("follow on spotify") ||
        contentLower.includes("spotify-follow") ||
        (await page.$('[data-action="spotify-follow"], .spotify-follow')) !== null;

      // Check for YouTube
      actions.youtubeSubscribe =
        contentLower.includes("subscribe on youtube") ||
        contentLower.includes("youtube-subscribe") ||
        (await page.$('[data-action="youtube-subscribe"], .youtube-subscribe')) !== null;

      // Check for comment (Hypeddit uses #sc_comment_text)
      const commentInput = await page.$('textarea[name="comment"], input[name="comment"], .comment-input, #sc_comment_text, input[name="sc_comment_text"]');
      actions.comment = !!commentInput;
    } catch (err) {
      warn("Error detecting required actions", { error: (err as Error).message });
    }

    return actions;
  }

  /**
   * Check if we can complete the required actions with available credentials
   */
  private canCompleteActions(
    actions: RequiredActions,
    credentials: GateCredentials
  ): { can: boolean; missing: string[] } {
    const missing: string[] = [];

    if (actions.email && !credentials.email) {
      missing.push("email");
    }

    if (actions.comment && !credentials.defaultComment) {
      missing.push("comment");
    }

    // SoundCloud actions require the user to be logged in to SoundCloud in the browser
    // For now, we'll warn but not require credentials
    if (actions.soundcloudFollow || actions.soundcloudLike || actions.soundcloudRepost) {
      // These actions will be attempted but may fail if not logged in
      debug("SoundCloud actions detected - will attempt but may require manual login");
    }

    return {
      can: missing.length === 0,
      missing,
    };
  }

  /**
   * Submit email to the gate form
   */
  private async submitEmail(page: Page, email: string, delay: number): Promise<void> {
    debug(`Submitting email: ${email}`);

    try {
      // Find email input
      const emailInput = await page.$(
        'input[type="email"], input[name="email"], input[placeholder*="email" i]'
      );

      if (emailInput) {
        await emailInput.fill(email);
        await delay(delay / 2);

        // Try to find and click submit button
        const submitButton = await page.$(
          'button[type="submit"], input[type="submit"], button:has-text("Submit"), button:has-text("Continue"), button:has-text("Unlock")'
        );

        if (submitButton) {
          await submitButton.click();
          await delay(delay);
        }
      }
    } catch (err) {
      warn("Failed to submit email", { error: (err as Error).message });
    }
  }

  /**
   * Submit a comment to the gate form
   */
  private async submitComment(page: Page, comment: string, delay: number): Promise<void> {
    debug("Submitting comment");

    try {
      // Hypeddit uses #sc_comment_text, others use various selectors
      const commentInput = await page.$(
        '#sc_comment_text, input[name="sc_comment_text"], textarea[name="comment"], input[name="comment"], .comment-input, textarea'
      );

      if (commentInput) {
        info("💬 Filling comment field...");
        await commentInput.fill(comment);
        await delay(delay / 2);

        // Look for submit button - Hypeddit often has form submission via enter or specific buttons
        const submitButton = await page.$(
          'button[type="submit"], button:has-text("Comment"), button:has-text("Post"), button:has-text("Submit"), input[type="submit"]'
        );

        if (submitButton) {
          info("💬 Clicking comment submit button...");
          await submitButton.click();
          await delay(delay);
        } else {
          // Try pressing Enter as some forms submit that way
          await commentInput.press('Enter');
          await delay(delay);
        }
      }
    } catch (err) {
      warn("Failed to submit comment", { error: (err as Error).message });
    }
  }

  /**
   * Handle SoundCloud follow action
   */
  private async handleSoundCloudFollow(page: Page, delay: number): Promise<boolean> {
    debug("Attempting SoundCloud follow action");

    try {
      // Look for follow button patterns
      const followButton = await page.$(
        '[data-action="soundcloud-follow"], .soundcloud-follow, button:has-text("Follow on SoundCloud")'
      );

      if (followButton) {
        await followButton.click();
        await delay(delay * 2); // Give time for popup/redirect

        // Handle potential popup window
        const pages = this.context!.pages();
        if (pages.length > 1) {
          const popup = pages[pages.length - 1];
          // Look for follow button in SoundCloud popup
          const scFollowBtn = await popup.$('.sc-button-follow, button:has-text("Follow")');
          if (scFollowBtn) {
            await scFollowBtn.click();
            await delay(delay);
          }
          await popup.close();
        }

        return true;
      }
    } catch (err) {
      warn("Failed to complete SoundCloud follow", { error: (err as Error).message });
    }

    return false;
  }

  /**
   * Handle SoundCloud like action
   */
  private async handleSoundCloudLike(page: Page, delay: number): Promise<boolean> {
    debug("Attempting SoundCloud like action");

    try {
      const likeButton = await page.$(
        '[data-action="soundcloud-like"], .soundcloud-like, button:has-text("Like on SoundCloud")'
      );

      if (likeButton) {
        await likeButton.click();
        await delay(delay * 2);

        // Handle potential popup
        const pages = this.context!.pages();
        if (pages.length > 1) {
          const popup = pages[pages.length - 1];
          const scLikeBtn = await popup.$('.sc-button-like, button:has-text("Like")');
          if (scLikeBtn) {
            await scLikeBtn.click();
            await delay(delay);
          }
          await popup.close();
        }

        return true;
      }
    } catch (err) {
      warn("Failed to complete SoundCloud like", { error: (err as Error).message });
    }

    return false;
  }

  /**
   * Handle SoundCloud repost action
   */
  private async handleSoundCloudRepost(page: Page, delay: number): Promise<boolean> {
    debug("Attempting SoundCloud repost action");

    try {
      const repostButton = await page.$(
        '[data-action="soundcloud-repost"], .soundcloud-repost, button:has-text("Repost on SoundCloud")'
      );

      if (repostButton) {
        await repostButton.click();
        await delay(delay * 2);

        // Handle potential popup
        const pages = this.context!.pages();
        if (pages.length > 1) {
          const popup = pages[pages.length - 1];
          const scRepostBtn = await popup.$('.sc-button-repost, button:has-text("Repost")');
          if (scRepostBtn) {
            await scRepostBtn.click();
            await delay(delay);
          }
          await popup.close();
        }

        return true;
      }
    } catch (err) {
      warn("Failed to complete SoundCloud repost", { error: (err as Error).message });
    }

    return false;
  }

  /**
   * Get the download after completing gate actions
   */
  private async getDownload(
    page: Page,
    options: BrowserOptions
  ): Promise<{ success: boolean; url?: string; filePath?: string; error?: string }> {
    debug("Looking for download button/link");

    try {
      // Wait for download button to become available
      await page.waitForSelector(
        'a[download], a:has-text("Download"), button:has-text("Download"), .download-button, [href*="download"]',
        { timeout: options.timeout }
      );

      // Set up download handling
      const downloadPromise = page.waitForEvent("download", { timeout: options.timeout });

      // Find and click download button
      const downloadButton = await page.$(
        'a[download], a:has-text("Download"), button:has-text("Download"), .download-button, [href*="download"]'
      );

      if (downloadButton) {
        // Check if it's a direct link
        const href = await downloadButton.getAttribute("href");
        if (href && (href.startsWith("http") || href.startsWith("//"))) {
          // Direct download link
          await downloadButton.click();

          try {
            const download = await downloadPromise;
            const suggestedFilename = download.suggestedFilename();
            const filePath = join(options.outputDir, suggestedFilename);

            await download.saveAs(filePath);

            return {
              success: true,
              url: href,
              filePath,
            };
          } catch {
            // Download didn't trigger, might be a direct link
            return {
              success: true,
              url: href.startsWith("//") ? `https:${href}` : href,
            };
          }
        } else {
          // Button that triggers download
          await downloadButton.click();

          const download = await downloadPromise;
          const suggestedFilename = download.suggestedFilename();
          const filePath = join(options.outputDir, suggestedFilename);

          await download.saveAs(filePath);

          return {
            success: true,
            filePath,
          };
        }
      }

      return {
        success: false,
        error: "Download button not found",
      };
    } catch (err) {
      return {
        success: false,
        error: (err as Error).message,
      };
    }
  }

}

// Export singleton
export const hypedditGateHandler = new HypedditGateHandler();
