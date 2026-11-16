<script setup lang="ts">
import { ref } from 'vue';
import { ask, type ApiMode } from './api';

type ChatMessage = { role: 'user' | 'assistant'; text: string };
const conversation = ref<ChatMessage[]>([
  { role: 'assistant', text: 'Hi! Send a message to test REST or ConnectRPC.' },
]);
const input = ref('Hello from Vue!');
const mode = ref<ApiMode>('rest');
const busy = ref(false);
const error = ref('');

async function send() {
  const text = input.value.trim();
  if (!text || busy.value) return;
  busy.value = true;
  error.value = '';
  conversation.value.push({ role: 'user', text });
  input.value = '';
  try {
    conversation.value.push({ role: 'assistant', text: await ask(text, mode.value) });
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <main class="page">
    <header>
      <div class="eyebrow">PROTOBUF + BUF · ONE CONTRACT</div>
      <h1>Chat protocol playground</h1>
      <p>Switch the transport below. REST, Connect JSON, Connect binary, and native gRPC share the same Python reply function.</p>
    </header>
    <section class="panel" aria-label="Chat demo">
      <div class="toolbar">
        <label for="mode">Client transport</label>
        <select id="mode" v-model="mode">
          <option value="rest">REST · JSON</option>
          <option value="connect-json">ConnectRPC · ProtoJSON</option>
          <option value="connect-binary">ConnectRPC · Protobuf</option>
        </select>
        <span class="status">● Demo reply</span>
      </div>
      <div class="messages" aria-live="polite">
        <div v-for="(message, index) in conversation" :key="index" :class="['message', message.role]">
          <small>{{ message.role === 'user' ? 'You' : 'AI assistant' }}</small>
          <div>{{ message.text }}</div>
        </div>
      </div>
      <p v-if="error" role="alert" class="error">{{ error }}</p>
      <form class="send-form" @submit.prevent="send">
        <input v-model="input" :disabled="busy" aria-label="Message" placeholder="Type a message…" />
        <button type="submit" :disabled="busy || !input.trim()">{{ busy ? 'Sending…' : 'Send' }}</button>
      </form>
    </section>
    <footer>
      <a href="http://127.0.0.1:8000/docs" target="_blank">FastAPI Swagger</a>
      <a href="/api/health" target="_blank">Health check</a>
      <code>/chat.v1.ChatService/Say</code>
    </footer>
  </main>
</template>
