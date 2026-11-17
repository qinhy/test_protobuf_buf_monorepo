#include "service.hpp"

#include <algorithm>
#include <cctype>
#include <stdexcept>
#include <string>
#include <string_view>

#include <google/protobuf/descriptor.h>
#include <google/protobuf/util/json_util.h>
#include <nlohmann/json.hpp>

#include "chat/v1/chat.pb.h"
#include "logic.hpp"

namespace chat::service {
namespace {

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

}  // namespace

grpc::Status GrpcChatService::Say(grpc::ServerContext* /*context*/,
                                  const chat::v1::SayRequest* request,
                                  chat::v1::SayResponse* response) {
  response->set_reply(chat::logic::GenerateReply(request->text()));
  return grpc::Status::OK;
}

void RegisterConnectRoutes(httplib::Server& server) {
  const auto* service_desc =
      chat::v1::SayRequest::descriptor()->file()->FindServiceByName(
          "ChatService");
  if (!service_desc) {
    throw std::runtime_error("ChatService descriptor not found");
  }
  const auto* method_desc = service_desc->FindMethodByName("Say");
  if (!method_desc) {
    throw std::runtime_error("Say method descriptor not found");
  }
  const std::string connect_path =
      "/" + ToStdString(service_desc->full_name()) + "/" +
      ToStdString(method_desc->name());

  server.Post(connect_path, [](const httplib::Request& req,
                               httplib::Response& res) {
    if (req.has_header("Content-Encoding")) {
      const std::string encoding =
          ToLowerAscii(TrimAscii(req.get_header_value("Content-Encoding")));
      if (!encoding.empty() && encoding != "identity") {
        SendConnectError(res, 415, "unimplemented",
                         "unsupported content-encoding: " + encoding);
        return;
      }
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
      proto_resp.set_reply(chat::logic::GenerateReply(proto_req.text()));
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
      proto_resp.set_reply(chat::logic::GenerateReply(proto_req.text()));
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
}

}  // namespace chat::service
