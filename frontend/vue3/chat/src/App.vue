<script setup lang="ts">
import { ref } from 'vue';
import { ask, isStreamingMode, streamChat, toStreamMode, type ApiMode } from './api';

type ChatMessage = { role: 'user' | 'assistant'; text: string };
const conversation = ref<ChatMessage[]>([
  { role: 'assistant', text: 'Hi! Send a message to test unary or streaming REST / ConnectRPC.' },
]);
const input = ref('Hello streaming API!');
const mode = ref<ApiMode>('connect-binary-stream');
const busy = ref(false);
const error = ref('');
let abortController: AbortController | null = null;

function cancelStream() {
  abortController?.abort();
}

async function send() {
  const text = input.value.trim();
  if (!text || busy.value) return;
  busy.value = true;
  error.value = '';
  conversation.value.push({ role: 'user', text });
  input.value = '';

  const streaming = isStreamingMode(mode.value);
  abortController = streaming ? new AbortController() : null;

  try {
    if (streaming) {
      const assistantIndex = conversation.value.push({ role: 'assistant', text: '' }) - 1;
      await streamChat(
        text,
        toStreamMode(mode.value),
        (partial) => {
          const message = conversation.value[assistantIndex];
          if (message) {
            message.text = partial;
          }
        },
        abortController?.signal,
      );
    } else {
      conversation.value.push({ role: 'assistant', text: await ask(text, mode.value) });
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      error.value = 'Stream cancelled.';
    } else {
      error.value = err instanceof Error ? err.message : String(err);
    }
  } finally {
    abortController = null;
    busy.value = false;
  }
}
</script>

<template>
  <main class="page">
    <header>
      <div class="eyebrow">PROTOBUF + BUF · ONE CONTRACT</div>
      <h1>Chat streaming playground</h1>
      <p>
        Switch the transport below. Unary and streaming REST (NDJSON), ConnectRPC, and native gRPC
        share the same Python event stream.
      </p>
    </header>
    <section class="panel" aria-label="Chat demo">
      <div class="toolbar">
        <label for="mode">Client transport</label>
        <select id="mode" v-model="mode" :disabled="busy">
          <option value="connect-binary-stream">ConnectRPC · Protobuf (Stream)</option>
          <option value="connect-json-stream">ConnectRPC · ProtoJSON (Stream)</option>
          <option value="rest-stream">REST · NDJSON (Stream)</option>
          <option value="rest">REST · JSON (Unary)</option>
          <option value="connect-json">ConnectRPC · ProtoJSON (Unary)</option>
          <option value="connect-binary">ConnectRPC · Protobuf (Unary)</option>
        </select>
        <span class="status">{{ busy ? '● Streaming…' : '● Demo reply' }}</span>
      </div>
      <div class="messages" aria-live="polite">
        <div v-for="(message, index) in conversation" :key="index" :class="['message', message.role]">
          <small>{{ message.role === 'user' ? 'You' : 'AI assistant' }}</small>
          <div>{{ message.text || '…' }}</div>
        </div>
      </div>
      <p v-if="error" role="alert" class="error">{{ error }}</p>
      <form class="send-form" @submit.prevent="send">
        <input v-model="input" :disabled="busy" aria-label="Message" placeholder="Type a message…" />
        <button v-if="busy && isStreamingMode(mode)" type="button" class="secondary" @click="cancelStream">
          Stop
        </button>
        <button type="submit" :disabled="busy || !input.trim()">{{ busy ? 'Sending…' : 'Send' }}</button>
      </form>
    </section>
    <footer>
      <a href="http://127.0.0.1:8000/docs" target="_blank">FastAPI Swagger</a>
      <a href="/api/health" target="_blank">Health check</a>
      <code>/api/chat/stream</code>
      <code>/chat.v1.ChatService/StreamSay</code>
    </footer>
  </main>
</template>
