#include "rest.hpp"

#include <algorithm>
#include <cctype>
#include <exception>
#include <stdexcept>
#include <string>
#include <string_view>

#include <google/protobuf/descriptor.h>
#include <google/protobuf/util/json_util.h>
#include <nlohmann/json.hpp>

#include "chat/v1/chat.pb.h"
#include "google/api/annotations.pb.h"
#include "logic.hpp"
#include "openapi_spec.hpp"
#include "serialization.hpp"

namespace chat::rest {
namespace {

constexpr const char* kSwaggerHtml = R"HTML(<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>chat - Swagger UI</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({
      url: '/openapi.json',
      dom_id: '#swagger-ui',
    });
  </script>
</body>
</html>
)HTML";

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

bool IsWhitespaceOnly(std::string_view text) {
  return std::all_of(text.begin(), text.end(), [](unsigned char ch) {
    return std::isspace(ch) != 0;
  });
}

struct HttpBinding {
  std::string method;
  std::string path;
};

HttpBinding ExtractHttpBinding(const google::protobuf::MethodDescriptor* method) {
  const auto& rule = method->options().GetExtension(google::api::http);
  switch (rule.pattern_case()) {
    case google::api::HttpRule::kPost:
      return {"POST", rule.post()};
    case google::api::HttpRule::kGet:
      return {"GET", rule.get()};
    case google::api::HttpRule::kPut:
      return {"PUT", rule.put()};
    case google::api::HttpRule::kDelete:
      return {"DELETE", rule.delete_()};
    case google::api::HttpRule::kPatch:
      return {"PATCH", rule.patch()};
    default:
      throw std::runtime_error(
          "google.api.http annotation missing on ChatService method");
  }
}

std::string BuildOpenApiJson(
    const google::protobuf::ServiceDescriptor* service,
    const google::protobuf::MethodDescriptor* say_method,
    const HttpBinding& say_binding,
    const google::protobuf::MethodDescriptor* stream_method,
    const HttpBinding& stream_binding) {
  const std::string_view source_spec(chat::generated::kSourceOpenApiJson);
  if (!source_spec.empty()) {
    auto parsed = nlohmann::json::parse(source_spec, nullptr, false);
    const std::string stream_lower = ToLowerAscii(stream_binding.method);
    if (!parsed.is_discarded() && parsed.contains("paths") &&
        parsed["paths"].is_object() &&
        parsed["paths"].contains(say_binding.path) &&
        parsed["paths"].contains(stream_binding.path) &&
        parsed["paths"][stream_binding.path].contains(stream_lower) &&
        parsed["paths"][stream_binding.path][stream_lower]
            ["responses"]["200"]["content"]
                .contains("application/x-ndjson")) {
      return std::string(source_spec);
    }
  }

  const std::string service_name = ToStdString(service->name());
  const std::string say_op_id =
      service_name + "_" + ToStdString(say_method->name());
  const std::string stream_op_id =
      service_name + "_" + ToStdString(stream_method->name());
  const std::string say_output_name =
      ToStdString(say_method->output_type()->full_name());
  const std::string event_output_name =
      ToStdString(stream_method->output_type()->full_name());
  const std::string stream_chunk_name = "StreamResultOf" + event_output_name;

  nlohmann::json request_body = nlohmann::json::object({
      {"required", true},
      {"content",
       nlohmann::json::object({
           {"application/json",
            nlohmann::json::object({
                {"schema",
                 nlohmann::json::object({
                     {"type", "object"},
                     {"properties",
                      nlohmann::json::object({
                          {"text",
                           nlohmann::json::object({
                               {"type", "string"},
                               {"description", "User's message."},
                           })},
                      })},
                 })},
            })},
       })},
  });

  nlohmann::json say_op = nlohmann::json::object({
      {"tags", nlohmann::json::array({service_name})},
      {"summary", "REST is generated from this HTTP annotation."},
      {"operationId", say_op_id},
      {"requestBody", request_body},
      {"responses",
       nlohmann::json::object({
           {"200",
            nlohmann::json::object({
                {"description", "A successful response."},
                {"content",
                 nlohmann::json::object({
                     {"application/json",
                      nlohmann::json::object({
                          {"schema",
                           nlohmann::json::object({
                               {"$ref", "#/components/schemas/" + say_output_name},
                           })},
                      })},
                 })},
            })},
       })},
  });

  nlohmann::json stream_op = nlohmann::json::object({
      {"tags", nlohmann::json::array({service_name})},
      {"summary", "Server-streaming API."},
      {"operationId", stream_op_id},
      {"requestBody", request_body},
      {"responses",
       nlohmann::json::object({
           {"200",
            nlohmann::json::object({
                {"description", "Incremental chat events"},
                {"content",
                 nlohmann::json::object({
                     {"application/x-ndjson",
                      nlohmann::json::object({
                          {"schema",
                           nlohmann::json::object({
                               {"type", "string"},
                               {"description",
                                "UTF-8 NDJSON stream, one JSON object per line."},
                           })},
                          {"x-ndjson-item-schema",
                           nlohmann::json::object({
                               {"$ref", "#/components/schemas/" + stream_chunk_name},
                           })},
                      })},
                 })},
            })},
       })},
  });

  nlohmann::json event_props = nlohmann::json::object({
      {"sequence", nlohmann::json::object({{"type", "integer"}})},
      {"start",
       nlohmann::json::object({
           {"type", "object"},
           {"properties",
            nlohmann::json::object({
                {"messageId", nlohmann::json::object({{"type", "string"}})},
            })},
       })},
      {"delta",
       nlohmann::json::object({
           {"type", "object"},
           {"properties",
            nlohmann::json::object({
                {"text", nlohmann::json::object({{"type", "string"}})},
            })},
       })},
      {"complete",
       nlohmann::json::object({
           {"type", "object"},
           {"properties",
            nlohmann::json::object({
                {"reply", nlohmann::json::object({{"type", "string"}})},
            })},
       })},
      {"failure",
       nlohmann::json::object({
           {"type", "object"},
           {"properties",
            nlohmann::json::object({
                {"code", nlohmann::json::object({{"type", "string"}})},
                {"message", nlohmann::json::object({{"type", "string"}})},
            })},
       })},
  });

  nlohmann::json schemas = nlohmann::json::object({
      {say_output_name,
       nlohmann::json::object({
           {"type", "object"},
           {"properties",
            nlohmann::json::object({
                {"reply",
                 nlohmann::json::object({
                     {"type", "string"},
                     {"description", "Assistant response."},
                 })},
            })},
       })},
      {event_output_name,
       nlohmann::json::object({
           {"type", "object"},
           {"properties", event_props},
       })},
      {stream_chunk_name,
       nlohmann::json::object({
           {"type", "object"},
           {"properties",
            nlohmann::json::object({
                {"result",
                 nlohmann::json::object({
                     {"$ref", "#/components/schemas/" + event_output_name},
                 })},
            })},
       })},
  });

  nlohmann::json spec = nlohmann::json::object({
      {"openapi", "3.1.0"},
      {"info", nlohmann::json::object({{"title", "chat"}, {"version", "1.0.0"}})},
      {"paths",
       nlohmann::json::object({
           {say_binding.path,
            nlohmann::json::object({{ToLowerAscii(say_binding.method), say_op}})},
           {stream_binding.path,
            nlohmann::json::object(
                {{ToLowerAscii(stream_binding.method), stream_op}})},
       })},
      {"components", nlohmann::json::object({{"schemas", schemas}})},
  });

  return spec.dump(2);
}

bool ParseAndValidateSayRequest(const httplib::Request& req,
                                httplib::Response& res,
                                chat::v1::SayRequest* out_req) {
  google::protobuf::util::JsonParseOptions parse_opts;
  parse_opts.ignore_unknown_fields = true;
  const auto parse_status = google::protobuf::util::JsonStringToMessage(
      req.body, out_req, parse_opts);
  if (!parse_status.ok()) {
    res.status = 422;
    nlohmann::json err = {{"detail", ToStdString(parse_status.message())}};
    res.set_content(err.dump(), "application/json");
    return false;
  }

  if (IsWhitespaceOnly(out_req->text())) {
    res.status = 422;
    nlohmann::json err = {{"detail", "text must be nonempty"}};
    res.set_content(err.dump(), "application/json");
    return false;
  }

  return true;
}

void HandleSayRest(const httplib::Request& req, httplib::Response& res) {
  chat::v1::SayRequest proto_req;
  if (!ParseAndValidateSayRequest(req, res, &proto_req)) {
    return;
  }

  chat::v1::SayResponse proto_resp;
  proto_resp.set_reply(chat::logic::CompleteReply(proto_req.text()));
  std::string out_json;
  const auto print_status =
      google::protobuf::util::MessageToJsonString(proto_resp, &out_json);
  if (!print_status.ok()) {
    res.status = 500;
    nlohmann::json err = {{"detail", "failed to serialize response"}};
    res.set_content(err.dump(), "application/json");
    return;
  }

  res.status = 200;
  res.set_content(out_json, "application/json");
}

void HandleStreamSayRest(const httplib::Request& req, httplib::Response& res) {
  chat::v1::SayRequest proto_req;
  if (!ParseAndValidateSayRequest(req, res, &proto_req)) {
    return;
  }

  res.status = 200;
  res.set_header("Cache-Control", "no-store");
  res.set_header("X-Accel-Buffering", "no");

  std::string prompt = proto_req.text();
  res.set_chunked_content_provider(
      "application/x-ndjson",
      [prompt = std::move(prompt)](size_t /*offset*/,
                                   httplib::DataSink& sink) -> bool {
        try {
          chat::logic::StreamReply(
              prompt, [&](const chat::events::ChatDomainEvent& event) -> bool {
                if (!sink.is_writable()) {
                  return false;
                }
                const std::string line =
                    chat::serialization::ToNdjsonLine(event);
                return sink.write(line.data(), line.size());
              });
        } catch (const std::exception& ex) {
          if (sink.is_writable()) {
            const std::string err_line =
                chat::serialization::NdjsonErrorLine(13, ex.what());
            sink.write(err_line.data(), err_line.size());
          }
        }
        sink.done();
        return true;
      });
}

void RegisterRoute(
    httplib::Server& server, const HttpBinding& binding,
    void (*handler)(const httplib::Request&, httplib::Response&)) {
  if (binding.method == "GET") {
    server.Get(binding.path, handler);
  } else if (binding.method == "PUT") {
    server.Put(binding.path, handler);
  } else if (binding.method == "DELETE") {
    server.Delete(binding.path, handler);
  } else if (binding.method == "PATCH") {
    server.Patch(binding.path, handler);
  } else {
    server.Post(binding.path, handler);
  }
}

}  // namespace

void RegisterRestRoutes(httplib::Server& server) {
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

  const HttpBinding say_binding = ExtractHttpBinding(say_desc);
  const HttpBinding stream_binding = ExtractHttpBinding(stream_desc);
  const std::string openapi_json = BuildOpenApiJson(
      service_desc, say_desc, say_binding, stream_desc, stream_binding);

  RegisterRoute(server, say_binding, HandleSayRest);
  RegisterRoute(server, stream_binding, HandleStreamSayRest);

  server.Get("/api/health",
             [](const httplib::Request& /*req*/, httplib::Response& res) {
               res.status = 200;
               res.set_content(R"({"status":"ok"})", "application/json");
             });

  server.Get("/openapi.json",
             [openapi_json](const httplib::Request& /*req*/,
                            httplib::Response& res) {
               res.status = 200;
               res.set_content(openapi_json, "application/json");
             });

  server.Get("/docs",
             [](const httplib::Request& /*req*/, httplib::Response& res) {
               res.status = 200;
               res.set_content(kSwaggerHtml, "text/html; charset=utf-8");
             });
}

}  // namespace chat::rest
