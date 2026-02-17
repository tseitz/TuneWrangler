# Flow-Based Gate Handling Guide

This guide explains how to use the flow-based system for handling download gates. Flows allow you to define browser automation sequences using JSON configuration files, making it easy to refine selectors without changing code.

## Overview

The flow system replaces hardcoded selector logic with data-driven configurations. You can:

- Capture full interaction sequences using Playwright codegen
- Convert codegen output to flow configurations
- Refine selectors incrementally by editing JSON files
- Handle multiple gate variations with different flows

## Workflow

### Step 1: Capture Interactions with Codegen

Use Playwright's codegen to capture your interactions:

```bash
npx playwright codegen https://hypeddit.com/track/your-track-id
```

This opens a browser window. Complete the full gate flow manually:

1. Fill in email (if required)
2. Click follow/like buttons
3. Handle any popups
4. Complete any other required actions
5. Click the download button

Codegen will generate TypeScript code showing all your interactions.

### Step 2: Save Codegen Output

Copy the generated code from the codegen window and save it to a file:

```bash
# Save to a file
cat > codegen-output.ts << 'EOF'
import { test, expect } from '@playwright/test';

test('test', async ({ page }) => {
  await page.goto('https://hypeddit.com/track/...');
  await page.click('button:has-text("Follow on SoundCloud")');
  // ... rest of the code
});
EOF
```

### Step 3: Convert to Flow Configuration

Use the `flow-convert` command to convert codegen output to a flow:

```bash
tunewrangler flow-convert codegen-output.ts --platform hypeddit
```

This will:
- Parse the codegen output
- Extract selectors and actions
- Create a flow configuration
- Save it to `src/config/flows/hypeddit.json`

### Step 4: Refine the Flow

Edit the generated JSON file to improve selectors:

```json
{
  "type": "click",
  "selector": "button:has-text('Download')",
  "description": "Click download button",
  "optional": false,
  "retry": 3
}
```

You can:
- Make selectors more specific or more general
- Add optional steps for variations
- Add retry logic for unreliable steps
- Add delays where needed

### Step 5: Test the Flow

Run the download command to test your flow:

```bash
tunewrangler soundcloud-download --url "https://soundcloud.com/user/sets/playlist" --headed
```

Use `--headed` to watch the browser and see if the flow works correctly.

## Flow Configuration Reference

See [src/config/flows/README.md](../src/config/flows/README.md) for complete flow format documentation.

## Common Patterns

### Handling Popups

```json
{
  "type": "click",
  "selector": "button:has-text('Follow on SoundCloud')",
  "description": "Click follow button"
},
{
  "type": "waitForPopup",
  "description": "Wait for popup",
  "timeout": 10000
},
{
  "type": "switchToPopup",
  "description": "Switch to popup"
},
{
  "type": "click",
  "selector": "button:has-text('Connect')",
  "description": "Click connect in popup"
},
{
  "type": "closePopup",
  "description": "Close popup"
}
```

### Using Credentials

```json
{
  "type": "fill",
  "selector": "input[type='email']",
  "value": "{{credentials.email}}",
  "description": "Fill email"
},
{
  "type": "fill",
  "selector": "textarea[name='comment']",
  "value": "{{credentials.defaultComment}}",
  "description": "Fill comment"
}
```

### Optional Steps

```json
{
  "type": "click",
  "selector": "button:has-text('Like')",
  "description": "Click like button",
  "optional": true
}
```

If this step fails, the flow continues.

### Retry Logic

```json
{
  "type": "click",
  "selector": "button:has-text('Download')",
  "description": "Click download",
  "retry": 3
}
```

The step will retry up to 3 times if it fails.

## Troubleshooting

### Flow Not Matching

If your flow isn't being used:

1. Check the URL patterns in your flow match the gate URL
2. Verify the platform is detected correctly
3. Check the flow file is in the correct location (`src/config/flows/`)

### Selectors Not Working

If selectors fail:

1. Use `--headed` mode to see what's happening
2. Inspect the page to find better selectors
3. Make selectors more specific or more general
4. Add `optional: true` for steps that might not always be present

### Flow Execution Failing

If the flow fails:

1. Check the logs for specific error messages
2. Verify all required credentials are configured
3. Test selectors manually in the browser console
4. Add delays between steps if needed
5. Make steps optional if they're not always required

## Advanced Usage

### Multiple Flows per Platform

You can define multiple flows in a single platform file:

```json
{
  "version": "1.0.0",
  "flows": [
    {
      "name": "Hypeddit Standard Flow",
      "urlPatterns": ["hypeddit.com"],
      "steps": [...]
    },
    {
      "name": "Hypeddit Alternative Flow",
      "urlPatterns": ["hype.to"],
      "steps": [...]
    }
  ]
}
```

### Custom Variables

Evaluate steps can set custom variables:

```json
{
  "type": "evaluate",
  "code": "document.querySelector('a').href",
  "selector": "gateUrl",
  "description": "Extract gate URL"
}
```

The result is stored in `variables.gateUrl` and can be used in subsequent steps with `{{gateUrl}}`.

## Migration from Hardcoded Logic

The system maintains backward compatibility:

1. **Flows are tried first** - If a matching flow exists, it's used
2. **Fallback to hardcoded logic** - If no flow matches or flow fails, the original hardcoded logic is used
3. **Gradual migration** - You can migrate platforms one at a time

To migrate a platform:

1. Create a flow using codegen
2. Test it thoroughly
3. Once working, the hardcoded logic becomes a fallback
4. Remove hardcoded logic when confident in the flow

## Examples

See the example flows in `src/config/flows/`:
- `hypeddit.json` - Hypeddit gate flow
- `toneden.json` - ToneDen gate flow
- `soundcloud-track.json` - SoundCloud track page flow

These can be used as starting points or references for creating your own flows.
