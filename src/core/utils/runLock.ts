import { TryLaterError } from "./errors.ts";

/**
 * Takes an OS file lock, or throws TryLaterError if another run still holds it after `waitMs`.
 * The OS drops the lock when its holder exits, crashed or not, so a lock is never left stale.
 * Returns the release function.
 */
export async function acquireRunLock(path: string, waitMs = 2000): Promise<() => Promise<void>> {
  const file = await Deno.open(path, { create: true, write: true });
  const locked = file.lock(true).then(() => true);
  let timer: number | undefined;
  const timedOut = new Promise<false>((resolve) => timer = setTimeout(() => resolve(false), waitMs));
  const acquired = await Promise.race([locked, timedOut]);
  clearTimeout(timer);

  if (!acquired) {
    // A lock still pending here would be held, unnoticed, once the other run finishes.
    locked.then(() => file.close(), () => file.close());
    throw new TryLaterError(`Another run holds ${path}. Nothing was changed.`);
  }

  await file.truncate();
  await file.write(new TextEncoder().encode(`${Deno.pid}\n`));
  return async () => {
    await file.unlock();
    file.close();
  };
}
