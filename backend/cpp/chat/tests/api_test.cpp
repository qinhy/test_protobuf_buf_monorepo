#include <httplib.h>
#include <grpcpp/grpcpp.h>
#include <gtest/gtest.h>
#include <nlohmann/json.hpp>

#include <cstdint>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

#include "app.hpp"
#include "chat/v1/chat.grpc.pb.h"
#include "logic.hpp"

namespace {

std::string EncodeConnectFrame(uint8_t flags, const std::string& payload) {
  std::string frame;
  frame.reserve(5 + payload.size());
  const uint32_t len = static_cast<uint32_t>(payload.size());
  frame.push_back(static_cast<char>(flags));
  frame.push_back(static_cast<char>((len >> 24) & 0xFF));
  frame.push_back(static_cast<char>((len >> 16) & 0xFF));
  frame.push_back(static_cast<char>((len >> 8) & 0xFF));
  frame.push_back(static_cast<char>(len & 0xFF));
  frame.append(payload);
  return frame;
}

std::vector<std::pair<uint8_t, std::string>> DecodeConnectFrames(
    const std::string& body) {
  std::vector<std::pair<uint8_t, std::string>> frames;
  size_t offset = 0;
  while (offset < body.size()) {
    EXPECT_LE(offset + 5, body.size());
    const uint8_t flags = static_cast<uint8_t>(body[offset]);
    const uint32_t len =
        (static_cast<uint32_t>(static_cast<uint8_t>(body[offset + 1])) << 24) |
        (static_cast<uint32_t>(static_cast<uint8_t>(body[offset + 2])) << 16) |
        (static_cast<uint32_t>(static_cast<uint8_t>(body[offset + 3])) << 8) |
        static_cast<uint32_t>(static_cast<uint8_t>(body[offset + 4]));
    offset += 5;
    EXPECT_LE(offset + len, body.size());
    frames.emplace_back(flags, body.substr(offset, len));
    offset += len;
  }
  return frames;
}

}  // namespace

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

  // REST POST /api/chat/stream -> 200 NDJSON
  {
    httplib::Headers headers = {{"Accept", "application/x-ndjson"}};
    auto res = http.Post("/api/chat/stream", headers, R"({"text":"stream"})",
                         "application/json");
    ASSERT_TRUE(res);
    EXPECT_EQ(res->status, 200);
    EXPECT_EQ(res->get_header_value("Content-Type"), "application/x-ndjson");

    std::istringstream iss(res->body);
    std::string line;
    std::vector<nlohmann::json> events;
    while (std::getline(iss, line)) {
      if (!line.empty()) {
        events.push_back(nlohmann::json::parse(line).at("result"));
      }
    }
    ASSERT_GE(events.size(), 3u);
    EXPECT_TRUE(events.front().contains("start"));
    std::string deltas;
    for (const auto& ev : events) {
      if (ev.contains("delta")) {
        deltas += ev.at("delta").at("text").get<std::string>();
      }
    }
    EXPECT_EQ(deltas, chat::logic::kReply);
    EXPECT_EQ(
        events.back().at("complete").at("reply").get<std::string>(),
        chat::logic::kReply);
  }

  // REST POST /api/chat & /api/chat/stream invalid/empty payloads -> 422
  for (const char* uri : {"/api/chat", "/api/chat/stream"}) {
    for (const char* payload :
         {R"({"text":"   "})", R"({})", R"({"text":null})", R"({"text":123})"}) {
      auto res = http.Post(uri, payload, "application/json");
      ASSERT_TRUE(res) << "uri: " << uri << " payload: " << payload;
      EXPECT_EQ(res->status, 422) << "uri: " << uri << " payload: " << payload;
    }
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
    EXPECT_TRUE(spec.at("paths").contains("/api/chat/stream"));
    EXPECT_TRUE(
        spec.at("paths").at("/api/chat/stream").at("post").at("responses")
            .at("200").at("content").contains("application/x-ndjson"));
  }

  // ConnectRPC JSON unary
  {
    auto res = http.Post("/chat.v1.ChatService/Say", R"({"text":"connect"})",
                         "application/json");
    ASSERT_TRUE(res);
    EXPECT_EQ(res->status, 200);
    auto json_body = nlohmann::json::parse(res->body);
    EXPECT_EQ(json_body.at("reply").get<std::string>(), chat::logic::kReply);
  }

  // ConnectRPC binary Protobuf unary
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

  // ConnectRPC binary streaming
  {
    chat::v1::SayRequest req;
    req.set_text("connect-stream");
    std::string req_bytes;
    ASSERT_TRUE(req.SerializeToString(&req_bytes));

    auto res = http.Post("/chat.v1.ChatService/StreamSay",
                         EncodeConnectFrame(0, req_bytes),
                         "application/connect+proto");
    ASSERT_TRUE(res);
    EXPECT_EQ(res->status, 200);
    auto frames = DecodeConnectFrames(res->body);
    ASSERT_GE(frames.size(), 3u);
    EXPECT_EQ(frames.back().first, 0x02);

    std::string deltas;
    std::string final_reply;
    for (size_t i = 0; i + 1 < frames.size(); ++i) {
      EXPECT_EQ(frames[i].first, 0);
      chat::v1::ChatEvent ev;
      ASSERT_TRUE(ev.ParseFromString(frames[i].second));
      if (ev.has_delta()) {
        deltas += ev.delta().text();
      } else if (ev.has_complete()) {
        final_reply = ev.complete().reply();
      }
    }
    EXPECT_EQ(deltas, chat::logic::kReply);
    EXPECT_EQ(final_reply, chat::logic::kReply);
  }

  // ConnectRPC JSON streaming
  {
    auto res = http.Post("/chat.v1.ChatService/StreamSay",
                         EncodeConnectFrame(0, R"({"text":"connect-json-stream"})"),
                         "application/connect+json");
    ASSERT_TRUE(res);
    EXPECT_EQ(res->status, 200);
    auto frames = DecodeConnectFrames(res->body);
    ASSERT_GE(frames.size(), 3u);
    EXPECT_EQ(frames.back().first, 0x02);
  }

  // ConnectRPC unsupported content-type -> 415
  {
    auto res = http.Post("/chat.v1.ChatService/Say", "hi", "text/plain");
    ASSERT_TRUE(res);
    EXPECT_EQ(res->status, 415);
  }

  // Native gRPC over HTTP/2 h2c (unary + streaming)
  {
    const std::string target =
        "127.0.0.1:" + std::to_string(app.grpc_port());
    auto channel =
        grpc::CreateChannel(target, grpc::InsecureChannelCredentials());
    auto stub = chat::v1::ChatService::NewStub(channel);

    {
      grpc::ClientContext ctx;
      chat::v1::SayRequest req;
      req.set_text("grpc");
      chat::v1::SayResponse resp;
      grpc::Status status = stub->Say(&ctx, req, &resp);
      ASSERT_TRUE(status.ok()) << status.error_message();
      EXPECT_EQ(resp.reply(), chat::logic::kReply);
    }

    {
      grpc::ClientContext ctx;
      chat::v1::SayRequest req;
      req.set_text("grpc-stream");
      auto reader = stub->StreamSay(&ctx, req);
      chat::v1::ChatEvent ev;
      std::string deltas;
      std::string final_reply;
      while (reader->Read(&ev)) {
        if (ev.has_delta()) {
          deltas += ev.delta().text();
        } else if (ev.has_complete()) {
          final_reply = ev.complete().reply();
        }
      }
      grpc::Status status = reader->Finish();
      ASSERT_TRUE(status.ok()) << status.error_message();
      EXPECT_EQ(deltas, chat::logic::kReply);
      EXPECT_EQ(final_reply, chat::logic::kReply);
    }
  }

  app.Stop();
}
