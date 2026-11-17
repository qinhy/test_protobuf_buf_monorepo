#include "rest.hpp"

#include <algorithm>
#include <cctype>
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

bool IsWhitespaceOnly(std::string_view text) {
  return std::all_of(text.begin(), text.end(), [](unsigned char ch) {
    return std::isspace(ch) != 0;
  });
}

struct HttpBinding {
  std::string method;
  std::string path;
};

HttpBinding ExtractSayHttpBinding(const google::protobuf::MethodDescriptor* method) {
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
          "google.api.http annotation missing on ChatService.Say");
  }
}

std::string BuildOpenApiJson(const google::protobuf::ServiceDescriptor* service,
                             const google::protobuf::MethodDescriptor* method,
                             const HttpBinding& binding) {
  const std::string_view source_spec(chat::generated::kSourceOpenApiJson);
  if (!source_spec.empty()) {
    auto parsed = nlohmann::json::parse(source_spec, nullptr, false);
    if (!parsed.is_discarded() && parsed.contains("paths") &&
        parsed["paths"].is_object() && parsed["paths"].contains(binding.path)) {
      return std::string(source_spec);
    }
  }

  std::string method_lower = binding.method;
  std::transform(method_lower.begin(), method_lower.end(), method_lower.begin(),
                 [](unsigned char ch) {
                   return static_cast<char>(std::tolower(ch));
                 });

  const std::string service_name = ToStdString(service->name());
  const std::string rpc_name = ToStdString(method->name());
  const std::string operation_id = service_name + "_" + rpc_name;
  const std::string output_full_name =
      ToStdString(method->output_type()->full_name());

  nlohmann::json spec = {
      {"openapi", "3.1.0"},
      {"info", {{"title", "chat"}, {"version", "1.0.0"}}},
      {"paths",
       nlohmann::json::object({
           {binding.path,
            nlohmann::json::object({
                {method_lower,
                 {
                     {"tags", nlohmann::json::array({service_name})},
                     {"summary", "REST is generated from this HTTP annotation."},
                     {"operationId", operation_id},
                     {"requestBody",
                      {
                          {"required", true},
                          {"content",
                           {{"application/json",
                             {{"schema",
                               {{"type", "object"},
                                {"properties",
                                 {{"text",
                                   {{"type", "string"},
                                    {"description", "User's message."}}}}}}}}}}},
                      }},
                     {"responses",
                      {
                          {"200",
                           {{"description", "A successful response."},
                            {"content",
                             {{"application/json",
                               {{"schema",
                                 {{"$ref", "#/components/schemas/" +
                                               output_full_name}}}}}}}}},
                      }},
                 }},
            })},
       })},
      {"components",
       {{"schemas",
         nlohmann::json::object({
             {output_full_name,
              {
                  {"type", "object"},
                  {"properties",
                   {{"reply",
                     {{"type", "string"},
                      {"description", "Assistant response."}}}}},
              }},
         })}}},
  };

  return spec.dump(2);
}

void HandleSayRest(const httplib::Request& req, httplib::Response& res) {
  chat::v1::SayRequest proto_req;
  google::protobuf::util::JsonParseOptions parse_opts;
  parse_opts.ignore_unknown_fields = true;
  const auto parse_status = google::protobuf::util::JsonStringToMessage(
      req.body, &proto_req, parse_opts);
  if (!parse_status.ok()) {
    res.status = 422;
    nlohmann::json err = {{"detail", ToStdString(parse_status.message())}};
    res.set_content(err.dump(), "application/json");
    return;
  }

  if (IsWhitespaceOnly(proto_req.text())) {
    res.status = 422;
    nlohmann::json err = {{"detail", "text must be nonempty"}};
    res.set_content(err.dump(), "application/json");
    return;
  }

  chat::v1::SayResponse proto_resp;
  proto_resp.set_reply(chat::logic::GenerateReply(proto_req.text()));
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

}  // namespace

void RegisterRestRoutes(httplib::Server& server) {
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
  const HttpBinding binding = ExtractSayHttpBinding(method_desc);
  const std::string openapi_json =
      BuildOpenApiJson(service_desc, method_desc, binding);

  if (binding.method == "GET") {
    server.Get(binding.path, HandleSayRest);
  } else if (binding.method == "PUT") {
    server.Put(binding.path, HandleSayRest);
  } else if (binding.method == "DELETE") {
    server.Delete(binding.path, HandleSayRest);
  } else if (binding.method == "PATCH") {
    server.Patch(binding.path, HandleSayRest);
  } else {
    server.Post(binding.path, HandleSayRest);
  }

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
