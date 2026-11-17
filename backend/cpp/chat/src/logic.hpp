#pragma once

#include <string>
#include <string_view>

namespace chat::logic {

inline constexpr const char* kReply =
    "Hello! I'm a demo AI assistant. This is a constant reply.";

/// Replace this function with an LLM call when ready.
std::string GenerateReply(std::string_view text);

}  // namespace chat::logic
