#pragma once

#include <cstdint>
#include <string>
#include <variant>

namespace chat::events {

struct Started {
  uint32_t sequence = 0;
  std::string message_id;
};

struct Delta {
  uint32_t sequence = 0;
  std::string text;
};

struct Completed {
  uint32_t sequence = 0;
  std::string reply;
};

struct Failed {
  uint32_t sequence = 0;
  std::string code;
  std::string message;
};

using ChatDomainEvent = std::variant<Started, Delta, Completed, Failed>;

inline uint32_t EventSequence(const ChatDomainEvent& event) {
  return std::visit([](const auto& item) { return item.sequence; }, event);
}

}  // namespace chat::events
