# Performance Optimization Guide

TuneWrangler includes comprehensive performance optimization features to handle large music libraries efficiently.

## Overview

The performance optimization system provides:

- **Batch Processing**: Process multiple files efficiently in controlled batches
- **LRU Caching**: Cache metadata and processing results for faster repeated operations
- **Memory Management**: Monitor and manage memory usage to prevent crashes
- **Streaming Processing**: Handle large files without loading them entirely into memory
- **Concurrency Control**: Limit parallel operations to optimize resource usage
- **Performance Monitoring**: Track operation metrics and identify bottlenecks

## Performance Features

### 1. Batch Processing

Batch processing groups multiple files together for more efficient processing:

```typescript
import { performanceOptimizer } from "../core/utils/performance.ts";

const results = await performanceOptimizer.processFilesOptimized(
  files,
  async (filename) => {
    // Process individual file
    return processedResult;
  },
  {
    batchSize: 20,        // Process 20 files per batch
    maxConcurrency: 3,    // Run 3 batches in parallel
    useCache: true,       // Enable caching
    onProgress: (processed, total) => {
      console.log(`Progress: ${processed}/${total}`);
    },
  }
);
```

**Benefits:**
- Reduces overhead from individual file operations
- Better resource utilization
- Progress tracking and reporting

### 2. LRU Caching

The LRU (Least Recently Used) cache stores frequently accessed data:

```typescript
import { LRUCache } from "../core/utils/performance.ts";

const cache = new LRUCache<string, Song>(1000, 300000); // 1000 items, 5 min TTL

// Store data
cache.set("song_key", songData);

// Retrieve data
const song = cache.get("song_key");

// Check if exists
if (cache.has("song_key")) {
  // Use cached data
}
```

**Benefits:**
- Faster repeated operations
- Reduced file I/O
- Automatic cleanup of old entries

### 3. Memory Management

Memory management prevents memory leaks and crashes:

```typescript
import { memoryManager } from "../core/utils/performance.ts";

// Register cleanup callbacks
memoryManager.registerCleanupCallback(() => {
  // Clear caches, close files, etc.
});

// Check memory usage periodically
const isHealthy = await memoryManager.checkMemoryUsage();
if (!isHealthy) {
  // Memory usage is high, take action
}

// Set memory threshold (default: 80%)
memoryManager.setMemoryThreshold(0.85); // 85%
```

**Benefits:**
- Prevents out-of-memory errors
- Automatic cleanup when memory usage is high
- Configurable thresholds

### 4. Streaming Processing

Streaming processes large files in chunks:

```typescript
import { StreamingProcessor } from "../core/utils/performance.ts";

const processor = new StreamingProcessor({
  bufferSize: 64 * 1024,    // 64KB buffer
  chunkSize: 1024 * 1024,   // 1MB chunks
  maxConcurrency: 3,
});

await processor.processFileStream(
  inputPath,
  outputPath,
  async (chunk) => {
    // Process chunk of data
    return processedChunk;
  }
);
```

**Benefits:**
- Handles files larger than available memory
- Consistent memory usage
- Better for audio file processing

### 5. Performance Monitoring

Track operation performance and identify bottlenecks:

```typescript
import { performanceMonitor } from "../core/utils/performance.ts";

// Start monitoring an operation
const operationId = performanceMonitor.startOperation("fileProcessing", {
  fileCount: 1000,
  batchSize: 20,
});

try {
  // Perform operation
  await processFiles();
  
  // End operation with success
  performanceMonitor.endOperation(operationId, {
    processed: 1000,
    errors: 0,
  });
} catch (error) {
  // End operation with error
  performanceMonitor.endOperation(operationId, { error });
}
```

**Benefits:**
- Identify slow operations
- Track resource usage
- Generate performance reports

## CLI Performance Commands

### Performance Report

View detailed performance metrics:

```bash
tunewrangler performance --report
```

**Output:**
```
📊 Performance Report
===================
Total Operations: 15
Total Duration: 2345.67ms
Average Duration: 156.38ms
Fastest Operation: 12.34ms
Slowest Operation: 456.78ms
Active Operations: 0

Top 5 Slowest Operations:
  fileProcessing: 456.78ms
  metadataExtraction: 234.56ms
  audioConversion: 123.45ms
  fileValidation: 67.89ms
  cacheUpdate: 34.56ms
```

### Monitor Active Operations

Monitor operations in real-time:

```bash
tunewrangler performance --monitor
```

**Output:**
```
👀 Active Operations Monitor
============================
Active Operations (3):
  1. fileProcessing_1234567890_abc123
  2. metadataExtraction_1234567891_def456
  3. audioConversion_1234567892_ghi789

Monitoring for 10 seconds...
[1.0s] Active operations: 3
[2.0s] Active operations: 2
[3.0s] Active operations: 1
[4.0s] Active operations: 0
✅ All operations completed
```

### Memory Monitoring

Check memory usage and thresholds:

```bash
tunewrangler performance --memory
```

**Output:**
```
🧠 Memory Monitoring
===================
Memory Status: ✅ Healthy
Memory threshold set to 85%
```

### Clear Performance Data

Clear all performance metrics and caches:

```bash
tunewrangler performance --clear
```

**Output:**
```
🧹 Clearing performance data...
✅ Performance data cleared
```

## Optimized Processors

TuneWrangler includes optimized versions of all processors:

### renameMusicOptimized

Enhanced version of the music renaming processor:

```bash
deno run --allow-read --allow-write src/processors/renameMusicOptimized.ts --move
```

**Features:**
- Batch processing with configurable batch size
- LRU caching for metadata
- Progress tracking
- Memory management
- Performance monitoring

### convertFlacsOptimized

Optimized FLAC conversion with streaming:

```bash
deno run --allow-read --allow-write src/processors/convertFlacsOptimized.ts --move
```

**Features:**
- Streaming file processing
- Lower concurrency for CPU-intensive operations
- Conversion caching
- Memory-efficient processing

### renameBandcampOptimized

Optimized Bandcamp file processing:

```bash
deno run --allow-read --allow-write src/processors/renameBandcampOptimized.ts --move
```

**Features:**
- Specialized caching for Bandcamp metadata
- Optimized batch sizes for typical Bandcamp files
- Enhanced error handling

## Performance Configuration

### Batch Size Optimization

Choose appropriate batch sizes based on your system:

```typescript
// For fast operations (file renaming)
const BATCH_SIZE = 50;

// For medium operations (metadata extraction)
const BATCH_SIZE = 20;

// For slow operations (audio conversion)
const BATCH_SIZE = 5;
```

### Concurrency Control

Adjust concurrency based on your system resources:

```typescript
// For I/O bound operations
const MAX_CONCURRENCY = 10;

// For CPU bound operations
const MAX_CONCURRENCY = 2;

// For memory intensive operations
const MAX_CONCURRENCY = 1;
```

### Cache Configuration

Configure cache size and TTL based on your usage:

```typescript
// Large cache for frequently accessed data
const CACHE_SIZE = 1000;
const TTL_MS = 300000; // 5 minutes

// Small cache for memory-constrained systems
const CACHE_SIZE = 100;
const TTL_MS = 60000; // 1 minute
```

## Best Practices

### 1. Monitor Performance

Regularly check performance metrics:

```bash
# Check performance before large operations
tunewrangler performance --report

# Monitor during operations
tunewrangler performance --monitor

# Check memory usage
tunewrangler performance --memory
```

### 2. Use Appropriate Batch Sizes

- **Small files (metadata)**: 50-100 files per batch
- **Medium files (audio processing)**: 10-20 files per batch
- **Large files (conversion)**: 5-10 files per batch

### 3. Configure Memory Thresholds

Set memory thresholds based on your system:

```typescript
// Conservative (prevents crashes)
memoryManager.setMemoryThreshold(0.7); // 70%

// Balanced (good performance)
memoryManager.setMemoryThreshold(0.8); // 80%

// Aggressive (maximum performance)
memoryManager.setMemoryThreshold(0.9); // 90%
```

### 4. Clear Performance Data Regularly

Clear old metrics to prevent memory buildup:

```bash
# Clear after large operations
tunewrangler performance --clear
```

### 5. Use Optimized Processors

Always use the optimized versions for better performance:

- `renameMusicOptimized.ts` instead of `renameMusic.ts`
- `convertFlacsOptimized.ts` instead of `convertFlacs.ts`
- `renameBandcampOptimized.ts` instead of `renameBandcamp.ts`

## Troubleshooting

### High Memory Usage

If you encounter high memory usage:

1. **Reduce batch size**: Lower the `BATCH_SIZE` in processors
2. **Reduce concurrency**: Lower the `MAX_CONCURRENCY` setting
3. **Clear caches**: Run `tunewrangler performance --clear`
4. **Check for memory leaks**: Monitor memory usage with `--memory` flag

### Slow Performance

If operations are slow:

1. **Increase batch size**: For I/O bound operations
2. **Increase concurrency**: For CPU bound operations with available resources
3. **Check disk I/O**: Ensure disk is not the bottleneck
4. **Review performance report**: Identify slow operations

### Cache Issues

If caching isn't working effectively:

1. **Increase cache size**: For frequently accessed data
2. **Adjust TTL**: Increase for stable data, decrease for changing data
3. **Check cache hits**: Monitor cache effectiveness in performance reports

## Advanced Usage

### Custom Performance Optimizer

Create custom optimizations for specific use cases:

```typescript
import { PerformanceOptimizer } from "../core/utils/performance.ts";

const customOptimizer = new PerformanceOptimizer();

// Custom processing with specific optimizations
const results = await customOptimizer.processFilesOptimized(
  files,
  processor,
  {
    batchSize: 25,
    maxConcurrency: 4,
    useCache: true,
    onProgress: (processed, total) => {
      // Custom progress handling
    },
  }
);
```

### Performance Metrics Analysis

Analyze performance metrics programmatically:

```typescript
import { performanceMonitor } from "../core/utils/performance.ts";

const metrics = performanceMonitor.getMetrics();
const activeOperations = performanceMonitor.getActiveOperations();

// Analyze slow operations
const slowOperations = metrics.filter(m => (m.duration || 0) > 1000);
console.log(`Found ${slowOperations.length} slow operations`);

// Check for bottlenecks
const avgDuration = metrics.reduce((sum, m) => sum + (m.duration || 0), 0) / metrics.length;
console.log(`Average operation duration: ${avgDuration.toFixed(2)}ms`);
```

This performance optimization system provides the tools needed to handle large music libraries efficiently while maintaining system stability and providing detailed insights into operation performance. 