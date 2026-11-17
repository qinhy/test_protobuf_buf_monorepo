#pragma once

#include <httplib.h>
#include <grpcpp/grpcpp.h>

#include <memory>
#include <string>
#include <thread>

#include "service.hpp"

namespace chat::app {

class ChatApp {
 public:
  ChatApp();
  ~ChatApp();

  ChatApp(const ChatApp&) = delete;
  ChatApp& operator=(const ChatApp&) = delete;

  /// Start HTTP (REST + ConnectRPC) and native gRPC servers.
  /// Pass port 0 in either address (e.g., "127.0.0.1:0") to bind an ephemeral port.
  void Start(const std::string& http_host, int http_port,
             const std::string& grpc_bind);

  void Stop();

  int http_port() const { return bound_http_port_; }
  int grpc_port() const { return bound_grpc_port_; }

 private:
  httplib::Server http_server_;
  chat::service::GrpcChatService grpc_service_;
  std::unique_ptr<grpc::Server> grpc_server_;
  std::thread http_thread_;
  int bound_http_port_ = 0;
  int bound_grpc_port_ = 0;
  bool running_ = false;
};

}  // namespace chat::app
