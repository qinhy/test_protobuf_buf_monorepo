#include "app.hpp"

#include <stdexcept>
#include <string>

#include "rest.hpp"
#include "service.hpp"

namespace chat::app {
namespace {

void ApplyCorsHeaders(const httplib::Request& req, httplib::Response& res) {
  if (!req.has_header("Origin")) {
    return;
  }
  const std::string origin = req.get_header_value("Origin");
  if (origin != "http://localhost:5173" &&
      origin != "http://127.0.0.1:5173") {
    return;
  }
  res.set_header("Access-Control-Allow-Origin", origin);
  res.set_header("Vary", "Origin");
  res.set_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS");
  if (req.has_header("Access-Control-Request-Headers")) {
    res.set_header("Access-Control-Allow-Headers",
                   req.get_header_value("Access-Control-Request-Headers"));
  } else {
    res.set_header("Access-Control-Allow-Headers", "*");
  }
}

void ConfigureHttpRouter(httplib::Server& server) {
  server.set_post_routing_handler(
      [](const httplib::Request& req, httplib::Response& res) {
        ApplyCorsHeaders(req, res);
      });

  server.Options(".*",
                 [](const httplib::Request& req, httplib::Response& res) {
                   ApplyCorsHeaders(req, res);
                   res.status = 204;
                 });

  // REST routes are registered before ConnectRPC routes, matching Python & Rust.
  chat::rest::RegisterRestRoutes(server);
  chat::service::RegisterConnectRoutes(server);
}

}  // namespace

ChatApp::ChatApp() { ConfigureHttpRouter(http_server_); }

ChatApp::~ChatApp() { Stop(); }

void ChatApp::Start(const std::string& http_host, int http_port,
                    const std::string& grpc_bind) {
  if (running_) {
    return;
  }

  if (http_port == 0) {
    bound_http_port_ = http_server_.bind_to_any_port(http_host);
    if (bound_http_port_ <= 0) {
      throw std::runtime_error("Could not bind HTTP server on " + http_host);
    }
  } else {
    if (!http_server_.bind_to_port(http_host, http_port)) {
      throw std::runtime_error("Could not bind HTTP server at " + http_host +
                               ":" + std::to_string(http_port));
    }
    bound_http_port_ = http_port;
  }

  grpc::ServerBuilder builder;
  int selected_grpc_port = 0;
  builder.AddListeningPort(grpc_bind, grpc::InsecureServerCredentials(),
                           &selected_grpc_port);
  builder.RegisterService(&grpc_service_);
  grpc_server_ = builder.BuildAndStart();
  if (!grpc_server_ || selected_grpc_port == 0) {
    http_server_.stop();
    throw std::runtime_error("Could not bind native gRPC at " + grpc_bind);
  }
  bound_grpc_port_ = selected_grpc_port;

  running_ = true;
  http_thread_ = std::thread([this]() { http_server_.listen_after_bind(); });
}

void ChatApp::Stop() {
  if (!running_) {
    return;
  }
  running_ = false;
  http_server_.stop();
  if (http_thread_.joinable()) {
    http_thread_.join();
  }
  if (grpc_server_) {
    grpc_server_->Shutdown();
    grpc_server_->Wait();
    grpc_server_.reset();
  }
}

}  // namespace chat::app
