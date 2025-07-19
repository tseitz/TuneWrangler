export class Semaphore {
  private permits: number;
  private tasks: (() => void)[] = [];

  constructor(permits: number) {
    this.permits = permits;
  }

  acquire(): Promise<void> {
    if (this.permits > 0) {
      this.permits--;
      return Promise.resolve();
    }

    return new Promise<void>((resolve) => {
      this.tasks.push(resolve);
    });
  }

  release(): void {
    this.permits++;

    if (this.tasks.length > 0 && this.permits > 0) {
      this.permits--;
      const nextTask = this.tasks.shift();
      if (nextTask) nextTask();
    }
  }
}
