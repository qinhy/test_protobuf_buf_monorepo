#pragma once

#include <httplib.h>

namespace chat::rest {

void RegisterRestRoutes(httplib::Server& server);

}  // namespace chat::rest
