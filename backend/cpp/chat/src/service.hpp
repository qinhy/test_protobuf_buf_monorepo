#pragma once

#include <httplib.h>
#include <grpcpp/grpcpp.h>

#include "chat/v1/chat.grpc.pb.h"

namespace chat::service {

class GrpcChatService final : public chat::v1::ChatService::Service {
 public:
  grpc::Status Say(grpc::ServerContext* context,
                   const chat::v1::SayRequest* request,
                   chat::v1::SayResponse* response) override;
};

void RegisterConnectRoutes(httplib::Server& server);

}  // namespace chat::service
