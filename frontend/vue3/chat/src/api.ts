// REST and Connect clients are generated from the same .proto contract.
import { createClient } from '@connectrpc/connect';
import { createConnectTransport } from '@connectrpc/connect-web';
import { ChatService } from './gen/chat/v1/chat_pb';
import { client as restTransport } from './gen/rest/client.gen';
import { chatServiceSay } from './gen/rest/sdk.gen';
import { streamRest } from './streaming';

export type ApiMode =
  | 'rest'
  | 'connect-json'
  | 'connect-binary'
  | 'rest-stream'
  | 'connect-json-stream'
  | 'connect-binary-stream';

export type StreamMode = 'rest' | 'connect-json' | 'connect-binary';

// Routes are proxied to FastAPI by Vite in local development.
const baseUrl = window.location.origin;
restTransport.setConfig({ baseUrl });

const connectJson = createClient(
  ChatService,
  createConnectTransport({
    baseUrl,
    useBinaryFormat: false,
  }),
);
const connectBinary = createClient(
  ChatService,
  createConnectTransport({
    baseUrl,
    useBinaryFormat: true,
  }),
);

export function isStreamingMode(mode: ApiMode): boolean {
  return mode.endsWith('-stream');
}

export async function ask(text: string, mode: ApiMode): Promise<string> {
  if (mode === 'rest') {
    const result = await chatServiceSay({ body: { text } });
    if (result.error) {
      throw new Error(JSON.stringify(result.error));
    }
    if (!result.data) {
      throw new Error('Empty REST response');
    }
    return result.data.reply ?? '';
  }
  const rpc = mode === 'connect-json' ? connectJson : connectBinary;
  const reply = await rpc.say({ text });
  return reply.reply;
}

export async function streamChat(
  text: string,
  mode: StreamMode,
  onUpdate: (partialReply: string) => void,
  signal?: AbortSignal,
): Promise<string> {
  let reply = '';
  let completed = false;
  let expectedSequence = 1;

  if (mode === 'rest') {
    for await (const event of streamRest(text, signal, baseUrl)) {
      if (event.sequence !== expectedSequence++) {
        throw new Error('Stream sequence mismatch');
      }
      if (event.delta) {
        reply += event.delta.text;
        onUpdate(reply);
      }
      if (event.complete) {
        reply = event.complete.reply;
        completed = true;
        onUpdate(reply);
      }
      if (event.failure) {
        throw new Error(event.failure.message);
      }
    }
  } else {
    const rpc = mode === 'connect-json' ? connectJson : connectBinary;
    for await (const event of rpc.streamSay({ text }, { signal })) {
      if (event.sequence !== expectedSequence++) {
        throw new Error('Stream sequence mismatch');
      }
      switch (event.payload.case) {
        case 'delta':
          reply += event.payload.value.text;
          onUpdate(reply);
          break;
        case 'complete':
          reply = event.payload.value.reply;
          completed = true;
          onUpdate(reply);
          break;
        case 'failure':
          throw new Error(event.payload.value.message);
        default:
          break;
      }
    }
  }

  if (!completed) {
    throw new Error('Stream ended without a complete event');
  }
  return reply;
}

export function toStreamMode(mode: ApiMode): StreamMode {
  if (mode === 'rest-stream' || mode === 'rest') return 'rest';
  if (mode === 'connect-json-stream' || mode === 'connect-json') return 'connect-json';
  return 'connect-binary';
}
