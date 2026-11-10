/**
 * Visibility-aware Polling Engine
 * Automatically pauses execution when tab is backgrounded / hidden.
 */

export class SmartPoller {
  constructor(pollFn, intervalMs) {
    this.pollFn = pollFn;
    this.intervalMs = intervalMs;
    this.timer = null;
    this.isRunning = false;
    this.handleVisibilityChange = this.handleVisibilityChange.bind(this);
  }

  start() {
    if (this.isRunning) return;
    this.isRunning = true;
    document.addEventListener("visibilitychange", this.handleVisibilityChange);
    this.execute();
  }

  stop() {
    this.isRunning = false;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    document.removeEventListener("visibilitychange", this.handleVisibilityChange);
  }

  async execute() {
    if (!this.isRunning) return;

    if (!document.hidden) {
      try {
        await this.pollFn();
      } catch (e) {
        console.warn("[POLLER WARNING]", e);
      }
    }

    if (this.isRunning) {
      this.timer = setTimeout(() => this.execute(), this.intervalMs);
    }
  }

  handleVisibilityChange() {
    if (!document.hidden && this.isRunning) {
      // Immediate poll on tab activation
      if (this.timer) clearTimeout(this.timer);
      this.execute();
    }
  }
}

