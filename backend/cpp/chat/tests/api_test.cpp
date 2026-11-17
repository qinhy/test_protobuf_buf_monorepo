#include <httplib.h>
#include <grpcpp/grpcpp.h>
#include <gtest/gtest.h>
#include <nlohmann/json.hpp>

#include <string>

#include "app.hpp"
#include "chat/v1/chat.grpc.pb.h"
#include "logic.hpp"

TEST(ApiTest, RestConnectAndNativeGrpcEndpoints) {
  chat::app::ChatApp app;
  app.Start("127.0.0.1", 0, "127.0.0.1:0");

  httplib::Client http("127.0.0.1", app.http_port());

  // REST POST /api/chat -> 200 + CORS header
  {
    httplib::Headers headers = {{"Origin", "http://localhost:5173"}};
    auto res = http.Post("/api/chat", headers, R"({"text":"rest"})",
                         "application/json");
    ASSERT_TRUE(res);
    EXPECT_EQ(res->status, 200);
    EXPECT_EQ(res->get_header_value("Access-Control-Allow-Origin"),
              "http://localhost:5173");
    auto json_body = nlohmann::json::parse(res->body);
    EXPECT_EQ(json_body.at("reply").get<std::string>(), chat::logic::kReply);
  }

  // REST POST /api/chat invalid/empty payloads -> 422
  for (const char* payload :
       {R"({"text":"   "})", R"({})", R"({"text":null})", R"({"text":123})"}) {
    auto res = http.Post("/api/chat", payload, "application/json");
    ASSERT_TRUE(res) << "payload: " << payload;
    EXPECT_EQ(res->status, 422) << "payload: " << payload;
  }

  // Health, /docs, and /openapi.json
  {
    auto health = http.Get("/api/health");
    ASSERT_TRUE(health);
    EXPECT_EQ(health->status, 200);
    EXPECT_EQ(nlohmann::json::parse(health->body),
              nlohmann::json({{"status", "ok"}}));

    auto docs = http.Get("/docs");
    ASSERT_TRUE(docs);
    EXPECT_EQ(docs->status, 200);
    EXPECT_NE(docs->body.find("/openapi.json"), std::string::npos);

    auto openapi = http.Get("/openapi.json");
    ASSERT_TRUE(openapi);
    EXPECT_EQ(openapi->status, 200);
    auto spec = nlohmann::json::parse(openapi->body);
    EXPECT_TRUE(spec.at("paths").contains("/api/chat"));
  }

  // ConnectRPC JSON
  {
    auto res = http.Post("/chat.v1.ChatService/Say", R"({"text":"connect"})",
                         "application/json");
    ASSERT_TRUE(res);
    EXPECT_EQ(res->status, 200);
    auto json_body = nlohmann::json::parse(res->body);
    EXPECT_EQ(json_body.at("reply").get<std::string>(), chat::logic::kReply);
  }

  // ConnectRPC binary Protobuf
  {
    chat::v1::SayRequest req;
    req.set_text("binary");
    std::string req_bytes;
    ASSERT_TRUE(req.SerializeToString(&req_bytes));

    httplib::Headers headers = {{"Accept", "application/proto"}};
    auto res = http.Post("/chat.v1.ChatService/Say", headers, req_bytes,
                         "application/proto");
    ASSERT_TRUE(res);
    EXPECT_EQ(res->status, 200);

    chat::v1::SayResponse resp;
    ASSERT_TRUE(resp.ParseFromString(res->body));
    EXPECT_EQ(resp.reply(), chat::logic::kReply);
  }

  // ConnectRPC unsupported content-type -> 415
  {
    auto res = http.Post("/chat.v1.ChatService/Say", "hi", "text/plain");
    ASSERT_TRUE(res);
    EXPECT_EQ(res->status, 415);
  }

  // Native gRPC over HTTP/2 h2c
  {
    const std::string target =
        "127.0.0.1:" + std::to_string(app.grpc_port());
    auto channel =
        grpc::CreateChannel(target, grpc::InsecureChannelCredentials());
    auto stub = chat::v1::ChatService::NewStub(channel);

    grpc::ClientContext ctx;
    chat::v1::SayRequest req;
    req.set_text("grpc");
    chat::v1::SayResponse resp;
    grpc::Status status = stub->Say(&ctx, req, &resp);
    ASSERT_TRUE(status.ok()) << status.error_message();
    EXPECT_EQ(resp.reply(), chat::logic::kReply);
  }

  app.Stop();
}
