export type RestChatEvent = {
  sequence: number;
  start?: { messageId: string };
  delta?: { text: string };
  complete?: { reply: string };
  failure?: { code: string; message: string };
};

type StreamEnvelope = {
  result?: RestChatEvent;
  error?: { code: number; message: string };
};

export async function* streamRest(
  text: string,
  signal?: AbortSignal,
  baseUrl: string = window.location.origin,
): AsyncGenerator<RestChatEvent> {
  const response = await fetch(`${baseUrl}/api/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/x-ndjson',
    },
    body: JSON.stringify({ text }),
    signal,
  });

  if (!response.ok || !response.body) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (payload.detail !== undefined) {
        detail = `${detail}: ${typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail)}`;
      }
    } catch {
      // Ignore non-JSON error bodies.
    }
    throw new Error(detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      while (true) {
        const position = buffer.indexOf('\n');
        if (position < 0) break;

        const line = buffer.slice(0, position).trim();
        buffer = buffer.slice(position + 1);

        if (!line) continue;

        const envelope = JSON.parse(line) as StreamEnvelope;
        if (envelope.error) {
          throw new Error(envelope.error.message);
        }
        if (!envelope.result) {
          throw new Error('Invalid stream envelope');
        }

        yield envelope.result;
      }
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      throw new Error('Stream ended with an incomplete line');
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
