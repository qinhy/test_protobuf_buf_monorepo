// REST and Connect clients are generated from the same .proto contract.
import { createClient } from '@connectrpc/connect';
import { createConnectTransport } from '@connectrpc/connect-web';
import { ChatService } from './gen/chat/v1/chat_pb';
import { client as restTransport } from './gen/rest/client.gen';
import { sendChat } from './gen/rest/sdk.gen';

export type ApiMode = 'rest' | 'connect-json' | 'connect-binary';

// Routes are proxied to FastAPI by Vite in local development.
const baseUrl = window.location.origin;
restTransport.setConfig({ baseUrl });

const connectJson = createClient(ChatService, createConnectTransport({
  baseUrl,
  useBinaryFormat: false,
}));
const connectBinary = createClient(ChatService, createConnectTransport({
  baseUrl,
  useBinaryFormat: true,
}));

export async function ask(text: string, mode: ApiMode): Promise<string> {
  if (mode === 'rest') {
    const result = await sendChat({ body: { text } });
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
