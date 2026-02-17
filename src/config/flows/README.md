# Flow Configuration

Flow configurations define step-by-step browser automation sequences for interacting with download gates and SoundCloud pages. These flows replace hardcoded selector logic with data-driven configurations that can be refined incrementally.

## Flow Format

Flows are stored as JSON files in this directory. Each file contains a `FlowConfig` object with one or more flows.

### Example Flow Structure

```json
{
  "version": "1.0.0",
  "flows": [
    {
      "name": "Hypeddit Standard Flow",
      "platform": "hypeddit",
      "urlPatterns": ["hypeddit.com", "hype.to"],
      "steps": [
        {
          "type": "fill",
          "selector": "input[type='email']",
          "value": "{{credentials.email}}",
          "description": "Fill email field"
        },
        {
          "type": "click",
          "selector": "button:has-text('Download')",
          "description": "Click download button"
        }
      ],
      "metadata": {
        "description": "Standard Hypeddit gate flow",
        "lastUpdated": "2026-01-25T00:00:00.000Z"
      }
    }
  ]
}
```

## Step Types

### `click`
Click an element.

```json
{
  "type": "click",
  "selector": "button:has-text('Download')",
  "description": "Click download button",
  "timeout": 10000,
  "optional": false,
  "retry": 3
}
```

### `fill`
Fill an input field with a value.

```json
{
  "type": "fill",
  "selector": "input[type='email']",
  "value": "{{credentials.email}}",
  "description": "Fill email field"
}
```

### `wait`
Wait for a specified duration.

```json
{
  "type": "wait",
  "delay": 2000,
  "description": "Wait 2 seconds"
}
```

### `waitForSelector`
Wait for an element to appear.

```json
{
  "type": "waitForSelector",
  "selector": "button:has-text('Download')",
  "description": "Wait for download button",
  "timeout": 30000
}
```

### `waitForPopup`
Wait for a popup window to open.

```json
{
  "type": "waitForPopup",
  "description": "Wait for SoundCloud popup",
  "timeout": 10000
}
```

### `switchToPopup`
Switch context to the most recently opened popup.

```json
{
  "type": "switchToPopup",
  "description": "Switch to popup window"
}
```

### `closePopup`
Close the current popup and return to the main page.

```json
{
  "type": "closePopup",
  "description": "Close popup"
}
```

### `waitForDownload`
Wait for a download to start.

```json
{
  "type": "waitForDownload",
  "description": "Wait for download",
  "timeout": 30000
}
```

### `navigate`
Navigate to a URL.

```json
{
  "type": "navigate",
  "url": "https://example.com",
  "description": "Navigate to page"
}
```

### `evaluate`
Execute JavaScript in the page context.

```json
{
  "type": "evaluate",
  "code": "document.querySelector('a').href",
  "selector": "result",
  "description": "Extract link URL"
}
```

## Variable Substitution

Flows support variable substitution using `{{variable}}` syntax:

- `{{credentials.email}}` - Email from credentials
- `{{credentials.soundcloudUsername}}` - SoundCloud username
- `{{credentials.defaultComment}}` - Default comment text
- `{{variableName}}` - Custom variables set by evaluate steps

## Step Properties

All steps support these optional properties:

- `timeout` - Timeout in milliseconds (default: 30000)
- `delay` - Delay after step completes in milliseconds
- `description` - Human-readable description
- `optional` - If true, failure doesn't stop the flow (default: false)
- `retry` - Number of retry attempts if step fails (default: 0)

## Creating Flows with Codegen

The easiest way to create flows is using Playwright's codegen:

1. **Run codegen:**
   ```bash
   npx playwright codegen https://hypeddit.com/track/...
   ```

2. **Interact with the page** - Complete the full flow manually (all clicks, fills, popup handling, etc.)

3. **Save the generated code** to a file (e.g., `codegen-output.ts`)

4. **Convert to flow:**
   ```bash
   tunewrangler flow-convert codegen-output.ts --platform hypeddit
   ```

5. **Refine selectors** - Edit the generated JSON file to improve selectors incrementally

## Refining Flows

After creating a flow from codegen, you can refine it:

1. **Edit the JSON file** directly in `src/config/flows/`

2. **Test the flow** by running the download command

3. **Adjust selectors** based on what works

4. **Add optional steps** for variations in gate layouts

5. **Add retry logic** for unreliable steps

## Platform Files

- `hypeddit.json` - Hypeddit gate flows
- `toneden.json` - ToneDen gate flows
- `soundcloud-track.json` - SoundCloud track page flows

Each platform file can contain multiple flows with different URL patterns for handling variations.

## Flow Matching

Flows are matched by URL patterns. When a gate URL is processed:

1. The system determines the platform from the URL
2. Loads the platform's flow file
3. Finds flows matching the URL patterns
4. Executes the first matching flow

If no flow matches, the system falls back to hardcoded logic.

## Best Practices

1. **Start with codegen** - Capture the full sequence first
2. **Refine incrementally** - Edit JSON, not code
3. **Use optional steps** - Handle variations gracefully
4. **Add descriptions** - Document what each step does
5. **Test thoroughly** - Verify flows work with different gate variations
6. **Version control** - Commit flow changes to track improvements
