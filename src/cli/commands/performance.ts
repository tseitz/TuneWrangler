#!/usr/bin/env -S deno run --allow-read --allow-write --allow-run --allow-net --allow-env --allow-sys

import { parse } from "https://deno.land/std@0.224.0/flags/mod.ts";
import { getLogger } from "../../core/utils/logger.ts";
import { performanceMonitor, performanceOptimizer, memoryManager } from "../../core/utils/performance.ts";

const logger = getLogger();

interface PerformanceFlags {
  report?: boolean;
  clear?: boolean;
  monitor?: boolean;
  optimize?: boolean;
  memory?: boolean;
  help?: boolean;
  _: string[];
}

async function performance(args: string[]): Promise<void> {
  // Parse the arguments including any flags
  const flags = parse(args, {
    boolean: ["report", "clear", "monitor", "optimize", "memory", "help"],
    alias: {
      help: "h",
    },
    string: [],
  }) as PerformanceFlags;

  if (flags.help) {
    showHelp();
    return;
  }

  logger.startOperation("performance", { args, flags });

  try {
    // Show performance report
    if (flags.report || flags._.includes("--report")) {
      await showPerformanceReport();
      return;
    }

    // Clear performance metrics
    if (flags.clear || flags._.includes("--clear")) {
      await clearPerformanceData();
      return;
    }

    // Monitor memory usage
    if (flags.memory || flags._.includes("--memory")) {
      await monitorMemory();
      return;
    }

    // Show optimization status
    if (flags.optimize || flags._.includes("--optimize")) {
      await showOptimizationStatus();
      return;
    }

    // Monitor active operations
    if (flags.monitor || flags._.includes("--monitor")) {
      await monitorActiveOperations();
      return;
    }

    // Default: show all performance information
    await showAllPerformanceInfo();
  } catch (error) {
    logger.error("Performance command failed", error as Error);
    throw error;
  }
}

async function showPerformanceReport(): Promise<void> {
  console.log("\n📊 Performance Report");
  console.log("===================");

  const report = performanceOptimizer.getPerformanceReport();
  console.log(report);

  // Show memory usage if available
  const memoryStatus = await memoryManager.checkMemoryUsage();
  console.log(`\n🧠 Memory Status: ${memoryStatus ? "✅ Healthy" : "⚠️ High usage"}`);
}

async function clearPerformanceData(): Promise<void> {
  console.log("\n🧹 Clearing performance data...");

  performanceOptimizer.clearAll();

  console.log("✅ Performance data cleared");
  logger.info("Performance data cleared");
}

async function monitorMemory(): Promise<void> {
  console.log("\n🧠 Memory Monitoring");
  console.log("===================");

  const status = await memoryManager.checkMemoryUsage();
  console.log(`Memory Status: ${status ? "✅ Healthy" : "⚠️ High usage"}`);

  // Set memory threshold
  memoryManager.setMemoryThreshold(0.85); // 85%
  console.log("Memory threshold set to 85%");

  logger.info("Memory monitoring completed", { status });
}

async function showOptimizationStatus(): Promise<void> {
  console.log("\n⚡ Optimization Status");
  console.log("=====================");

  const activeOperations = performanceMonitor.getActiveOperations();
  const metrics = performanceMonitor.getMetrics();

  console.log(`Active Operations: ${activeOperations.length}`);
  console.log(`Total Metrics Collected: ${metrics.length}`);

  if (activeOperations.length > 0) {
    console.log("\nActive Operations:");
    activeOperations.forEach((op, index) => {
      console.log(`  ${index + 1}. ${op}`);
    });
  }

  if (metrics.length > 0) {
    const recentMetrics = metrics.slice(-5);
    console.log("\nRecent Operations:");
    recentMetrics.forEach((metric) => {
      const duration = metric.duration ? `${metric.duration.toFixed(2)}ms` : "in progress";
      console.log(`  ${metric.operation}: ${duration}`);
    });
  }

  logger.info("Optimization status displayed", {
    activeOperations: activeOperations.length,
    totalMetrics: metrics.length,
  });
}

async function monitorActiveOperations(): Promise<void> {
  console.log("\n👀 Active Operations Monitor");
  console.log("============================");

  const activeOperations = performanceMonitor.getActiveOperations();

  if (activeOperations.length === 0) {
    console.log("No active operations");
    return;
  }

  console.log(`Active Operations (${activeOperations.length}):`);
  activeOperations.forEach((operation, index) => {
    console.log(`  ${index + 1}. ${operation}`);
  });

  // Monitor for 10 seconds
  console.log("\nMonitoring for 10 seconds...");
  const startTime = Date.now();

  const interval = setInterval(() => {
    const currentActive = performanceMonitor.getActiveOperations();
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

    console.log(`[${elapsed}s] Active operations: ${currentActive.length}`);

    if (currentActive.length === 0) {
      console.log("✅ All operations completed");
      clearInterval(interval);
    }
  }, 1000);

  // Stop monitoring after 10 seconds
  setTimeout(() => {
    clearInterval(interval);
    console.log("⏰ Monitoring timeout reached");
  }, 10000);

  logger.info("Active operations monitoring started");
}

async function showAllPerformanceInfo(): Promise<void> {
  console.log("\n🎵 TuneWrangler Performance Information");
  console.log("=====================================");

  // Show performance report
  await showPerformanceReport();

  // Show optimization status
  await showOptimizationStatus();

  // Show memory status
  await monitorMemory();

  // Show usage tips
  console.log("\n💡 Performance Tips:");
  console.log("  • Use --batch-size to control processing batch size");
  console.log("  • Use --max-concurrency to limit parallel operations");
  console.log("  • Monitor memory usage with --memory flag");
  console.log("  • Clear old metrics with --clear flag");
  console.log("  • Use optimized processors for better performance");

  logger.info("All performance information displayed");
}

function showHelp(): void {
  console.log(`
🎵 TuneWrangler Performance Command

Monitor and optimize TuneWrangler performance.

USAGE:
  tunewrangler performance [options]

OPTIONS:
  --report, -r        Show detailed performance report
  --clear, -c         Clear all performance metrics and cache
  --monitor, -m       Monitor active operations in real-time
  --optimize, -o      Show optimization status and recommendations
  --memory, -mem      Monitor memory usage and thresholds
  --help, -h          Show this help message

EXAMPLES:
  tunewrangler performance                    # Show all performance info
  tunewrangler performance --report          # Show detailed report
  tunewrangler performance --monitor         # Monitor active operations
  tunewrangler performance --clear           # Clear performance data
  tunewrangler performance --memory          # Check memory usage

PERFORMANCE FEATURES:
  • Batch processing for efficient file operations
  • LRU caching for metadata and processing results
  • Memory management and cleanup
  • Real-time operation monitoring
  • Performance metrics collection
  • Streaming file processing
  • Concurrency control

For more information, see the documentation.
`);
}

export { performance };
