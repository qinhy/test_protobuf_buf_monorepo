#include "logic.hpp"

#include <atomic>
#include <cstdio>
#include <stdexcept>
#include <thread>

namespace chat::logic {
namespace {

std::atomic<uint64_t> g_message_seq{1};

std::string NextMessageId() {
  const uint64_t id = g_message_seq.fetch_add(1, std::memory_order_relaxed);
  char buf[32];
  std::snprintf(buf, sizeof(buf), "msg-%06llu",
                static_cast<unsigned long long>(id));
  return std::string(buf);
}

// Advance across `max_codepoints` UTF-8 code points without splitting a rune.
std::size_t NextUtf8ChunkLength(std::string_view text,
                                std::size_t max_codepoints) {
  std::size_t pos = 0;
  std::size_t count = 0;
  while (pos < text.size() && count < max_codepoints) {
    const unsigned char lead = static_cast<unsigned char>(text[pos]);
    std::size_t char_len = 1;
    if ((lead & 0x80) == 0) {
      char_len = 1;
    } else if ((lead & 0xE0) == 0xC0) {
      char_len = 2;
    } else if ((lead & 0xF0) == 0xE0) {
      char_len = 3;
    } else if ((lead & 0xF8) == 0xF0) {
      char_len = 4;
    }
    pos = (pos + char_len <= text.size()) ? (pos + char_len) : text.size();
    ++count;
  }
  return pos;
}

}  // namespace

std::string GenerateReply(std::string_view /*text*/) {
  // The input is deliberately unused by this constant-reply demo.
  return kReply;
}

void StreamReply(
    std::string_view /*text*/,
    const std::function<bool(const chat::events::ChatDomainEvent&)>& emit,
    std::size_t chunk_chars, std::chrono::milliseconds delay) {
  uint32_t sequence = 1;
  if (!emit(chat::events::Started{sequence, NextMessageId()})) {
    return;
  }

  const std::size_t step = chunk_chars > 0 ? chunk_chars : 1;
  std::string_view remaining(kReply);
  while (!remaining.empty()) {
    if (delay.count() > 0) {
      std::this_thread::sleep_for(delay);
    }
    const std::size_t len = NextUtf8ChunkLength(remaining, step);
    const std::string chunk(remaining.substr(0, len));
    remaining.remove_prefix(len);
    ++sequence;
    if (!emit(chat::events::Delta{sequence, chunk})) {
      return;
    }
  }

  ++sequence;
  emit(chat::events::Completed{sequence, kReply});
}

std::string CompleteReply(std::string_view text) {
  std::string final_reply;
  bool completed = false;
  StreamReply(
      text,
      [&](const chat::events::ChatDomainEvent& event) {
        if (const auto* done = std::get_if<chat::events::Completed>(&event)) {
          final_reply = done->reply;
          completed = true;
        } else if (const auto* fail =
                       std::get_if<chat::events::Failed>(&event)) {
          throw std::runtime_error(fail->code + ": " + fail->message);
        }
        return true;
      },
      4, std::chrono::milliseconds(0));

  if (!completed) {
    throw std::runtime_error("Chat stream ended without a completion event");
  }
  return final_reply;
}

}  // namespace chat::logic
