#pragma once

#include <chrono>
#include <cstddef>
#include <functional>
#include <string>
#include <string_view>

#include "events.hpp"

namespace chat::logic {

inline constexpr const char* kReply =
    "Hello! I'm a demo AI assistant. This is a constant reply.";

/// Replace this function (and StreamReply) with an LLM call when ready.
std::string GenerateReply(std::string_view text);

/// Stream transport-neutral chat events to `emit`.
/// Stops early if `emit` returns false.
void StreamReply(
    std::string_view text,
    const std::function<bool(const chat::events::ChatDomainEvent&)>& emit,
    std::size_t chunk_chars = 4,
    std::chrono::milliseconds delay = std::chrono::milliseconds(50));

/// Consume StreamReply and return the final reply for unary endpoints.
std::string CompleteReply(std::string_view text);

}  // namespace chat::logic
