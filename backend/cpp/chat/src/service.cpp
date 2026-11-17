#include "service.hpp"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <exception>
#include <stdexcept>
#include <string>
#include <string_view>

#include <google/protobuf/descriptor.h>
#include <google/protobuf/util/json_util.h>
#include <nlohmann/json.hpp>

#include "chat/v1/chat.pb.h"
#include "logic.hpp"
#include "serialization.hpp"

namespace chat::service {
namespace {

constexpr uint8_t kConnectFlagEndStream = 0x02;

template <typename StringLike>
std::string ToStdString(const StringLike& s) {
  return std::string(s.data(), s.size());
}

std::string ToLowerAscii(std::string_view input) {
  std::string out(input);
  std::transform(out.begin(), out.end(), out.begin(), [](unsigned char ch) {
    return static_cast<char>(std::tolower(ch));
  });
  return out;
}

std::string TrimAscii(std::string_view input) {
  size_t start = 0;
  while (start < input.size() &&
         std::isspace(static_cast<unsigned char>(input[start]))) {
    ++start;
  }
  size_t end = input.size();
  while (end > start &&
         std::isspace(static_cast<unsigned char>(input[end - 1]))) {
    --end;
  }
  return std::string(input.substr(start, end - start));
}

std::string MediaType(const httplib::Request& req) {
  if (!req.has_header("Content-Type")) {
    return "";
  }
  std::string raw = req.get_header_value("Content-Type");
  auto semi = raw.find(';');
  if (semi != std::string::npos) {
    raw = raw.substr(0, semi);
  }
  return ToLowerAscii(TrimAscii(raw));
}

void SendConnectError(httplib::Response& res, int status, std::string_view code,
                      std::string_view message) {
  res.status = status;
  nlohmann::json err = {{"code", code}, {"message", message}};
  res.set_content(err.dump(), "application/json");
}

bool ValidateContentEncoding(const httplib::Request& req,
                             httplib::Response& res) {
  if (req.has_header("Content-Encoding")) {
    const std::string encoding =
        ToLowerAscii(TrimAscii(req.get_header_value("Content-Encoding")));
    if (!encoding.empty() && encoding != "identity") {
      SendConnectError(res, 415, "unimplemented",
                       "unsupported content-encoding: " + encoding);
      return false;
    }
  }
  return true;
}

std::string EncodeConnectFrame(uint8_t flags, std::string_view payload) {
  std::string frame;
  frame.reserve(5 + payload.size());
  const uint32_t len = static_cast<uint32_t>(payload.size());
  frame.push_back(static_cast<char>(flags));
  frame.push_back(static_cast<char>((len >> 24) & 0xFF));
  frame.push_back(static_cast<char>((len >> 16) & 0xFF));
  frame.push_back(static_cast<char>((len >> 8) & 0xFF));
  frame.push_back(static_cast<char>(len & 0xFF));
  frame.append(payload.data(), payload.size());
  return frame;
}

bool DecodeConnectFrame(std::string_view body, uint8_t* out_flags,
                        std::string_view* out_payload, std::string* out_err) {
  if (body.size() < 5) {
    *out_err = "truncated connect envelope header";
    return false;
  }
  const uint8_t flags = static_cast<uint8_t>(body[0]);
  const uint32_t len =
      (static_cast<uint32_t>(static_cast<uint8_t>(body[1])) << 24) |
      (static_cast<uint32_t>(static_cast<uint8_t>(body[2])) << 16) |
      (static_cast<uint32_t>(static_cast<uint8_t>(body[3])) << 8) |
      static_cast<uint32_t>(static_cast<uint8_t>(body[4]));
  if (body.size() != 5 + static_cast<size_t>(len)) {
    *out_err = "connect frame length mismatch";
    return false;
  }
  *out_flags = flags;
  *out_payload = body.substr(5, len);
  return true;
}

}  // namespace

grpc::Status GrpcChatService::Say(grpc::ServerContext* /*context*/,
                                  const chat::v1::SayRequest* request,
                                  chat::v1::SayResponse* response) {
  response->set_reply(chat::logic::CompleteReply(request->text()));
  return grpc::Status::OK;
}

grpc::Status GrpcChatService::StreamSay(
    grpc::ServerContext* context, const chat::v1::SayRequest* request,
    grpc::ServerWriter<chat::v1::ChatEvent>* writer) {
  chat::logic::StreamReply(
      request->text(),
      [&](const chat::events::ChatDomainEvent& event) -> bool {
        if (context->IsCancelled()) {
          return false;
        }
        return writer->Write(chat::serialization::ToProto(event));
      });
  if (context->IsCancelled()) {
    return grpc::Status(grpc::StatusCode::CANCELLED, "Client cancelled");
  }
  return grpc::Status::OK;
}

void RegisterConnectRoutes(httplib::Server& server) {
  const auto* service_desc =
      chat::v1::SayRequest::descriptor()->file()->FindServiceByName(
          "ChatService");
  if (!service_desc) {
    throw std::runtime_error("ChatService descriptor not found");
  }
  const auto* say_desc = service_desc->FindMethodByName("Say");
  if (!say_desc) {
    throw std::runtime_error("Say method descriptor not found");
  }
  const auto* stream_desc = service_desc->FindMethodByName("StreamSay");
  if (!stream_desc) {
    throw std::runtime_error("StreamSay method descriptor not found");
  }

  const std::string service_full_name = ToStdString(service_desc->full_name());
  const std::string connect_say_path =
      "/" + service_full_name + "/" + ToStdString(say_desc->name());
  const std::string connect_stream_path =
      "/" + service_full_name + "/" + ToStdString(stream_desc->name());

  server.Post(connect_say_path, [](const httplib::Request& req,
                                   httplib::Response& res) {
    if (!ValidateContentEncoding(req, res)) {
      return;
    }

    const std::string content_type = MediaType(req);
    if (content_type.empty()) {
      SendConnectError(res, 415, "unimplemented",
                       "missing content-type header");
      return;
    }

    if (content_type == "application/json") {
      chat::v1::SayRequest proto_req;
      google::protobuf::util::JsonParseOptions parse_opts;
      parse_opts.ignore_unknown_fields = true;
      const auto status = google::protobuf::util::JsonStringToMessage(
          req.body, &proto_req, parse_opts);
      if (!status.ok()) {
        SendConnectError(res, 400, "invalid_argument",
                         "invalid JSON request: " +
                             ToStdString(status.message()));
        return;
      }

      chat::v1::SayResponse proto_resp;
      proto_resp.set_reply(chat::logic::CompleteReply(proto_req.text()));
      std::string out_json;
      const auto print_status =
          google::protobuf::util::MessageToJsonString(proto_resp, &out_json);
      if (!print_status.ok()) {
        SendConnectError(res, 500, "internal",
                         "failed to serialize JSON response");
        return;
      }
      res.status = 200;
      res.set_content(out_json, "application/json");
      return;
    }

    if (content_type == "application/proto" ||
        content_type == "application/protobuf") {
      chat::v1::SayRequest proto_req;
      if (!proto_req.ParseFromString(req.body)) {
        SendConnectError(res, 400, "invalid_argument",
                         "invalid protobuf request");
        return;
      }

      chat::v1::SayResponse proto_resp;
      proto_resp.set_reply(chat::logic::CompleteReply(proto_req.text()));
      std::string out_bytes;
      if (!proto_resp.SerializeToString(&out_bytes)) {
        SendConnectError(res, 500, "internal",
                         "failed to serialize protobuf response");
        return;
      }
      res.status = 200;
      res.set_content(out_bytes, "application/proto");
      return;
    }

    SendConnectError(res, 415, "unimplemented",
                     "unsupported content-type: " + content_type);
  });

  server.Post(connect_stream_path, [](const httplib::Request& req,
                                      httplib::Response& res) {
    if (!ValidateContentEncoding(req, res)) {
      return;
    }

    const std::string content_type = MediaType(req);
    if (content_type.empty()) {
      SendConnectError(res, 415, "unimplemented",
                       "missing content-type header");
      return;
    }

    bool is_binary = false;
    if (content_type == "application/connect+proto" ||
        content_type == "application/connect+protobuf") {
      is_binary = true;
    } else if (content_type == "application/connect+json") {
      is_binary = false;
    } else {
      SendConnectError(res, 415, "unimplemented",
                       "unsupported streaming content-type: " + content_type);
      return;
    }

    uint8_t flags = 0;
    std::string_view payload;
    std::string frame_err;
    if (!DecodeConnectFrame(req.body, &flags, &payload, &frame_err)) {
      SendConnectError(res, 400, "invalid_argument", frame_err);
      return;
    }
    if (flags != 0) {
      SendConnectError(res, 415, "unimplemented",
                       "unsupported connect frame flags");
      return;
    }

    chat::v1::SayRequest proto_req;
    if (is_binary) {
      if (!proto_req.ParseFromArray(payload.data(),
                                    static_cast<int>(payload.size()))) {
        SendConnectError(res, 400, "invalid_argument",
                         "invalid protobuf request");
        return;
      }
    } else {
      google::protobuf::util::JsonParseOptions parse_opts;
      parse_opts.ignore_unknown_fields = true;
      const auto status = google::protobuf::util::JsonStringToMessage(
          std::string(payload), &proto_req, parse_opts);
      if (!status.ok()) {
        SendConnectError(res, 400, "invalid_argument",
                         "invalid JSON request: " +
                             ToStdString(status.message()));
        return;
      }
    }

    res.status = 200;
    std::string prompt = proto_req.text();
    res.set_chunked_content_provider(
        content_type,
        [prompt = std::move(prompt), is_binary](
            size_t /*offset*/, httplib::DataSink& sink) -> bool {
          bool ok = true;
          try {
            chat::logic::StreamReply(
                prompt,
                [&](const chat::events::ChatDomainEvent& event) -> bool {
                  if (!sink.is_writable()) {
                    ok = false;
                    return false;
                  }
                  std::string payload_bytes;
                  if (is_binary) {
                    if (!chat::serialization::ToProto(event)
                             .SerializeToString(&payload_bytes)) {
                      throw std::runtime_error("failed to serialize ChatEvent");
                    }
                  } else {
                    payload_bytes = chat::serialization::ToProtoJson(event);
                  }
                  const std::string frame = EncodeConnectFrame(0, payload_bytes);
                  ok = sink.write(frame.data(), frame.size());
                  return ok;
                });
            if (ok && sink.is_writable()) {
              const std::string eos =
                  EncodeConnectFrame(kConnectFlagEndStream, "{}");
              sink.write(eos.data(), eos.size());
            }
          } catch (const std::exception& ex) {
            if (sink.is_writable()) {
              nlohmann::json err = {
                  {"error", {{"code", "internal"}, {"message", ex.what()}}}};
              const std::string eos =
                  EncodeConnectFrame(kConnectFlagEndStream, err.dump());
              sink.write(eos.data(), eos.size());
            }
          }
          sink.done();
          return true;
        });
  });
}

}  // namespace chat::service
