import { getLogger } from "./logger.ts";
import { PerformanceError } from "./errors.ts";

const logger = getLogger();

/**
 * Performance monitoring and optimization utilities
 */

export interface PerformanceMetrics {
  operation: string;
  startTime: number;
  endTime?: number;
  duration?: number;
  memoryUsage?: {
    heapUsed: number;
    heapTotal: number;
    external: number;
  };
  fileCount?: number;
  bytesProcessed?: number;
  errors?: number;
  warnings?: number;
}

export interface BatchConfig {
  maxBatchSize: number;
  maxConcurrency: number;
  timeoutMs: number;
  retryAttempts: number;
}

export interface CacheConfig {
  maxSize: number;
  ttlMs: number;
  cleanupIntervalMs: number;
}

export interface StreamConfig {
  bufferSize: number;
  chunkSize: number;
  maxConcurrency: number;
}

/**
 * Performance monitor for tracking operations
 */
export class PerformanceMonitor {
  private metrics: Map<string, PerformanceMetrics> = new Map();
  private activeOperations: Set<string> = new Set();

  startOperation(operation: string, context?: Record<string, any>): string {
    const id = `${operation}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    this.metrics.set(id, {
      operation,
      startTime: performance.now(),
      ...context,
    });

    this.activeOperations.add(id);

    logger.debug(`🚀 Started operation: ${operation}`, { operationId: id, context });

    return id;
  }

  endOperation(id: string, context?: Record<string, any>): PerformanceMetrics {
    const metric = this.metrics.get(id);
    if (!metric) {
      throw new PerformanceError(`Operation not found: ${id}`);
    }

    metric.endTime = performance.now();
    metric.duration = metric.endTime - metric.startTime;
    metric.memoryUsage = this.getMemoryUsage();

    if (context) {
      Object.assign(metric, context);
    }

    this.activeOperations.delete(id);

    logger.info(`✅ Completed operation: ${metric.operation}`, {
      operationId: id,
      duration: `${metric.duration.toFixed(2)}ms`,
      memoryUsage: metric.memoryUsage,
      ...context,
    });

    return metric;
  }

  getMemoryUsage() {
    // Note: performance.memory is not available in Deno by default
    // This is a placeholder for when memory APIs become available
    return undefined;
  }

  getMetrics(): PerformanceMetrics[] {
    return Array.from(this.metrics.values());
  }

  getActiveOperations(): string[] {
    return Array.from(this.activeOperations);
  }

  clearMetrics(): void {
    this.metrics.clear();
    this.activeOperations.clear();
  }

  generateReport(): string {
    const metrics = this.getMetrics();
    if (metrics.length === 0) return "No performance metrics available";

    const totalDuration = metrics.reduce((sum, m) => sum + (m.duration || 0), 0);
    const avgDuration = totalDuration / metrics.length;
    const maxDuration = Math.max(...metrics.map((m) => m.duration || 0));
    const minDuration = Math.min(...metrics.map((m) => m.duration || 0));

    return `
Performance Report:
==================
Total Operations: ${metrics.length}
Total Duration: ${totalDuration.toFixed(2)}ms
Average Duration: ${avgDuration.toFixed(2)}ms
Fastest Operation: ${minDuration.toFixed(2)}ms
Slowest Operation: ${maxDuration.toFixed(2)}ms
Active Operations: ${this.activeOperations.size}

Top 5 Slowest Operations:
${metrics
  .sort((a, b) => (b.duration || 0) - (a.duration || 0))
  .slice(0, 5)
  .map((m) => `  ${m.operation}: ${m.duration?.toFixed(2)}ms`)
  .join("\n")}
    `.trim();
  }
}

/**
 * LRU Cache for file metadata and processing results
 */
export class LRUCache<K, V> {
  private cache = new Map<K, { value: V; timestamp: number }>();
  private maxSize: number;
  private ttlMs: number;

  constructor(maxSize: number = 1000, ttlMs: number = 300000) {
    // 5 minutes default TTL
    this.maxSize = maxSize;
    this.ttlMs = ttlMs;
  }

  set(key: K, value: V): void {
    // Remove expired entries
    this.cleanup();

    // Remove oldest entry if at capacity
    if (this.cache.size >= this.maxSize) {
      const oldestKey = this.cache.keys().next().value;
      if (oldestKey !== undefined) {
        this.cache.delete(oldestKey);
      }
    }

    this.cache.set(key, { value, timestamp: Date.now() });
  }

  get(key: K): V | undefined {
    const entry = this.cache.get(key);
    if (!entry) return undefined;

    // Check if expired
    if (Date.now() - entry.timestamp > this.ttlMs) {
      this.cache.delete(key);
      return undefined;
    }

    // Move to end (LRU behavior)
    this.cache.delete(key);
    this.cache.set(key, entry);

    return entry.value;
  }

  has(key: K): boolean {
    return this.get(key) !== undefined;
  }

  delete(key: K): boolean {
    return this.cache.delete(key);
  }

  clear(): void {
    this.cache.clear();
  }

  size(): number {
    this.cleanup();
    return this.cache.size;
  }

  private cleanup(): void {
    const now = Date.now();
    for (const [key, entry] of this.cache.entries()) {
      if (now - entry.timestamp > this.ttlMs) {
        this.cache.delete(key);
      }
    }
  }
}

/**
 * Batch processor for handling multiple operations efficiently
 */
export class BatchProcessor<T, R> {
  private config: BatchConfig;
  private queue: Array<{ item: T; resolve: (value: R) => void; reject: (error: Error) => void }> = [];
  private processing = false;

  constructor(config: Partial<BatchConfig> = {}) {
    this.config = {
      maxBatchSize: 50,
      maxConcurrency: 5,
      timeoutMs: 30000,
      retryAttempts: 3,
      ...config,
    };
  }

  async process(
    items: T[],
    processor: (batch: T[]) => Promise<R[]>,
    onProgress?: (processed: number, total: number) => void
  ): Promise<R[]> {
    const results: R[] = [];
    let processed = 0;

    // Split items into batches
    const batches: T[][] = [];
    for (let i = 0; i < items.length; i += this.config.maxBatchSize) {
      batches.push(items.slice(i, i + this.config.maxBatchSize));
    }

    // Process batches with concurrency control
    const semaphore = new Semaphore(this.config.maxConcurrency);

    const batchPromises = batches.map(async (batch) => {
      await semaphore.acquire();
      try {
        const batchResults = await processor(batch);
        results.push(...batchResults);
        processed += batch.length;
        onProgress?.(processed, items.length);
        return batchResults;
      } finally {
        semaphore.release();
      }
    });

    await Promise.all(batchPromises);
    return results;
  }

  async addToQueue(item: T): Promise<R> {
    return new Promise((resolve, reject) => {
      this.queue.push({ item, resolve, reject });
      this.processQueue();
    });
  }

  private async processQueue(): Promise<void> {
    if (this.processing || this.queue.length === 0) return;

    this.processing = true;
    const batch = this.queue.splice(0, this.config.maxBatchSize);

    try {
      // Process batch (implementation depends on specific use case)
      // This is a placeholder - actual implementation would depend on the processor
      for (const { item, resolve, reject } of batch) {
        try {
          // Placeholder processing
          resolve(item as unknown as R);
        } catch (error) {
          reject(error as Error);
        }
      }
    } finally {
      this.processing = false;
      if (this.queue.length > 0) {
        this.processQueue();
      }
    }
  }
}

/**
 * Streaming file processor for large files
 */
export class StreamingProcessor {
  private config: StreamConfig;

  constructor(config: Partial<StreamConfig> = {}) {
    this.config = {
      bufferSize: 64 * 1024, // 64KB
      chunkSize: 1024 * 1024, // 1MB
      maxConcurrency: 3,
      ...config,
    };
  }

  async processFileStream(
    inputPath: string,
    outputPath: string,
    processor: (chunk: Uint8Array) => Promise<Uint8Array>
  ): Promise<void> {
    const inputFile = await Deno.open(inputPath);
    const outputFile = await Deno.open(outputPath, { write: true, create: true, truncate: true });

    try {
      const buffer = new Uint8Array(this.config.bufferSize);
      let bytesRead: number | null;

      while ((bytesRead = await inputFile.read(buffer)) !== null) {
        const chunk = buffer.subarray(0, bytesRead);
        const processedChunk = await processor(chunk);
        await outputFile.write(processedChunk);
      }
    } finally {
      inputFile.close();
      outputFile.close();
    }
  }

  async processDirectoryStream(
    inputDir: string,
    outputDir: string,
    processor: (inputPath: string, outputPath: string) => Promise<void>,
    onProgress?: (processed: number, total: number) => void
  ): Promise<void> {
    const files: string[] = [];

    for await (const entry of Deno.readDir(inputDir)) {
      if (entry.isFile) {
        files.push(entry.name);
      }
    }

    const semaphore = new Semaphore(this.config.maxConcurrency);
    let processed = 0;

    const promises = files.map(async (filename) => {
      await semaphore.acquire();
      try {
        const inputPath = `${inputDir}/${filename}`;
        const outputPath = `${outputDir}/${filename}`;
        await processor(inputPath, outputPath);
        processed++;
        onProgress?.(processed, files.length);
      } finally {
        semaphore.release();
      }
    });

    await Promise.all(promises);
  }
}

/**
 * Memory management utilities
 */
export class MemoryManager {
  private static instance: MemoryManager;
  private memoryThreshold = 0.8; // 80% of available memory
  private cleanupCallbacks: (() => void)[] = [];

  static getInstance(): MemoryManager {
    if (!MemoryManager.instance) {
      MemoryManager.instance = new MemoryManager();
    }
    return MemoryManager.instance;
  }

  registerCleanupCallback(callback: () => void): void {
    this.cleanupCallbacks.push(callback);
  }

  async checkMemoryUsage(): Promise<boolean> {
    // Note: performance.memory is not available in Deno by default
    // This is a placeholder for when memory APIs become available
    return true;
  }

  private async performCleanup(): Promise<void> {
    logger.info("🧹 Performing memory cleanup");

    // Run all cleanup callbacks
    for (const callback of this.cleanupCallbacks) {
      try {
        callback();
      } catch (error) {
        logger.error("Cleanup callback failed", error as Error);
      }
    }

    // Force garbage collection if available
    if (typeof (globalThis as any).gc === "function") {
      (globalThis as any).gc();
    }
  }

  private formatBytes(bytes: number): string {
    const sizes = ["Bytes", "KB", "MB", "GB"];
    if (bytes === 0) return "0 Bytes";
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round((bytes / Math.pow(1024, i)) * 100) / 100 + " " + sizes[i];
  }

  setMemoryThreshold(threshold: number): void {
    this.memoryThreshold = Math.max(0.1, Math.min(0.95, threshold));
  }
}

/**
 * Semaphore for concurrency control
 */
class Semaphore {
  private permits: number;
  private waitQueue: Array<() => void> = [];

  constructor(permits: number) {
    this.permits = permits;
  }

  async acquire(): Promise<void> {
    if (this.permits > 0) {
      this.permits--;
      return Promise.resolve();
    }

    return new Promise<void>((resolve) => {
      this.waitQueue.push(resolve);
    });
  }

  release(): void {
    if (this.waitQueue.length > 0) {
      const resolve = this.waitQueue.shift()!;
      resolve();
    } else {
      this.permits++;
    }
  }
}

/**
 * Performance optimization utilities
 */
export class PerformanceOptimizer {
  private monitor: PerformanceMonitor;
  private cache: LRUCache<string, any>;
  private memoryManager: MemoryManager;

  constructor() {
    this.monitor = new PerformanceMonitor();
    this.cache = new LRUCache(1000, 300000); // 1000 items, 5 minutes TTL
    this.memoryManager = MemoryManager.getInstance();
  }

  /**
   * Optimized file processing with caching and batching
   */
  async processFilesOptimized<T>(
    files: string[],
    processor: (file: string) => Promise<T>,
    options: {
      batchSize?: number;
      maxConcurrency?: number;
      useCache?: boolean;
      onProgress?: (processed: number, total: number) => void;
    } = {}
  ): Promise<T[]> {
    const { batchSize = 50, maxConcurrency = 5, useCache = true, onProgress } = options;

    const operationId = this.monitor.startOperation("processFilesOptimized", {
      fileCount: files.length,
      batchSize,
      maxConcurrency,
    });

    try {
      const batchProcessor = new BatchProcessor<T, T>({
        maxBatchSize: batchSize,
        maxConcurrency,
      });

      const results: T[] = [];
      let processed = 0;

      // Process files in batches
      for (let i = 0; i < files.length; i += batchSize) {
        const batch = files.slice(i, i + batchSize);

        const batchResults = await Promise.all(
          batch.map(async (file) => {
            // Check cache first
            if (useCache) {
              const cached = this.cache.get(file);
              if (cached !== undefined) {
                return cached;
              }
            }

            // Process file
            const result = await processor(file);

            // Cache result
            if (useCache) {
              this.cache.set(file, result);
            }

            processed++;
            onProgress?.(processed, files.length);

            // Check memory usage periodically
            if (processed % 100 === 0) {
              await this.memoryManager.checkMemoryUsage();
            }

            return result;
          })
        );

        results.push(...batchResults);
      }

      this.monitor.endOperation(operationId, {
        processed,
        cacheHits: useCache ? this.cache.size() : 0,
      });

      return results;
    } catch (error) {
      this.monitor.endOperation(operationId, { error: error as Error });
      throw error;
    }
  }

  /**
   * Get performance report
   */
  getPerformanceReport(): string {
    return this.monitor.generateReport();
  }

  /**
   * Clear all caches and metrics
   */
  clearAll(): void {
    this.cache.clear();
    this.monitor.clearMetrics();
  }
}

// Export singleton instances
export const performanceMonitor = new PerformanceMonitor();
export const performanceOptimizer = new PerformanceOptimizer();
export const memoryManager = MemoryManager.getInstance();
