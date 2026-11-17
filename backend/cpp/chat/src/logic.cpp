#include "logic.hpp"

namespace chat::logic {

std::string GenerateReply(std::string_view /*text*/) {
  // The input is deliberately unused by this constant-reply demo.
  return kReply;
}

}  // namespace chat::logic
