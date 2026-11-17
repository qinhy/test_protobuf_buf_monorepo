//! Standalone C++ backend entry point: `chat-server`.
//!
//! REST /docs and /api/chat:          HTTP/1.1 on port 8000 (HOST:PORT)
//! Connect /chat.v1.ChatService/Say: HTTP/1.1 on port 8000 (HOST:PORT)
//! Native gRPC:                      HTTP/2 h2c on port 50051 (GRPC_BIND)

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <iostream>
#include <string>
#include <thread>

#include "app.hpp"

namespace {

std::atomic<bool> g_stop_requested{false};

void HandleSignal(int /*sig*/) { g_stop_requested.store(true); }

std::string EnvOrDefault(const char* name, const char* fallback) {
  if (const char* value = std::getenv(name); value && *value != '\0') {
    return value;
  }
  return fallback;
}

}  // namespace

int main() {
  std::signal(SIGINT, HandleSignal);
  std::signal(SIGTERM, HandleSignal);

  const std::string host = EnvOrDefault("HOST", "127.0.0.1");
  const int port = std::stoi(EnvOrDefault("PORT", "8000"));
  const std::string grpc_bind = EnvOrDefault("GRPC_BIND", "127.0.0.1:50051");

  try {
    chat::app::ChatApp app;
    app.Start(host, port, grpc_bind);

    std::cout << "[http] REST + ConnectRPC listening at http://" << host << ":"
              << app.http_port() << std::endl;
    std::cout << "[grpc] native HTTP/2 (h2c) listening at " << grpc_bind
              << std::endl;

    while (!g_stop_requested.load()) {
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    app.Stop();
  } catch (const std::exception& ex) {
    std::cerr << "[error] " << ex.what() << std::endl;
    return 1;
  }

  return 0;
}
