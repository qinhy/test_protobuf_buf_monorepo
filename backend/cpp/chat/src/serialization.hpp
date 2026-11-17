#pragma once

#include <string>
#include <string_view>

#include "chat/v1/chat.pb.h"
#include "events.hpp"

namespace chat::serialization {

chat::v1::ChatEvent ToProto(const chat::events::ChatDomainEvent& event);

std::string ToProtoJson(const chat::events::ChatDomainEvent& event);

std::string ToNdjsonLine(const chat::events::ChatDomainEvent& event);

std::string NdjsonErrorLine(int code, std::string_view message);

}  // namespace chat::serialization
