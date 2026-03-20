import { api } from "./api";
import type { UIEventPayload } from "./types";

export function track(
  payload: Omit<UIEventPayload, "occurred_at"> & {
    context?: Record<string, string | number | boolean | null | undefined>;
  },
) {
  const event: UIEventPayload = {
    ...payload,
    occurred_at: new Date().toISOString(),
  };

  void api.track(event).catch(() => {
    // Tracking should never block the analyst workflow.
  });
}
