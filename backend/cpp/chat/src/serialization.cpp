#include "serialization.hpp"

#include <stdexcept>
#include <variant>

#include <google/protobuf/util/json_util.h>
#include <nlohmann/json.hpp>

namespace chat::serialization {
namespace {

template <class... Ts>
struct Overloaded : Ts... {
  using Ts::operator()...;
};
template <class... Ts>
Overloaded(Ts...) -> Overloaded<Ts...>;

}  // namespace

chat::v1::ChatEvent ToProto(const chat::events::ChatDomainEvent& event) {
  chat::v1::ChatEvent out;
  std::visit(
      Overloaded{
          [&](const chat::events::Started& started) {
            out.set_sequence(started.sequence);
            out.mutable_start()->set_message_id(started.message_id);
          },
          [&](const chat::events::Delta& delta) {
            out.set_sequence(delta.sequence);
            out.mutable_delta()->set_text(delta.text);
          },
          [&](const chat::events::Completed& completed) {
            out.set_sequence(completed.sequence);
            out.mutable_complete()->set_reply(completed.reply);
          },
          [&](const chat::events::Failed& failed) {
            out.set_sequence(failed.sequence);
            out.mutable_failure()->set_code(failed.code);
            out.mutable_failure()->set_message(failed.message);
          },
      },
      event);
  return out;
}

std::string ToProtoJson(const chat::events::ChatDomainEvent& event) {
  const chat::v1::ChatEvent proto_event = ToProto(event);
  std::string out;
  const auto status =
      google::protobuf::util::MessageToJsonString(proto_event, &out);
  if (!status.ok()) {
    throw std::runtime_error("Failed to serialize ChatEvent to ProtoJSON");
  }
  return out;
}

std::string ToNdjsonLine(const chat::events::ChatDomainEvent& event) {
  return "{\"result\":" + ToProtoJson(event) + "}\n";
}

std::string NdjsonErrorLine(int code, std::string_view message) {
  nlohmann::json err = {
      {"error", {{"code", code}, {"message", std::string(message)}}}};
  return err.dump() + "\n";
}

}  // namespace chat::serialization
