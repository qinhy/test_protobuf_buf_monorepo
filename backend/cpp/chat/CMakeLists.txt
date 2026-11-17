cmake_minimum_required(VERSION 3.24)

if(WIN32 AND NOT DEFINED VCPKG_INSTALL_OPTIONS)
  if(DEFINED ENV{LOCALAPPDATA} AND NOT "$ENV{LOCALAPPDATA}" STREQUAL "")
    file(TO_CMAKE_PATH "$ENV{LOCALAPPDATA}/vb" _vcpkg_short_buildtrees)
    set(VCPKG_INSTALL_OPTIONS "--x-buildtrees-root=${_vcpkg_short_buildtrees}" CACHE STRING "Extra options passed to vcpkg install")
  endif()
endif()

project(chat_backend VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(DEFINED ENV{CHAT_PROTO_DIR} AND NOT "$ENV{CHAT_PROTO_DIR}" STREQUAL "")
  set(_default_proto_dir "$ENV{CHAT_PROTO_DIR}")
else()
  set(_default_proto_dir "${CMAKE_CURRENT_SOURCE_DIR}/../../../proto/chat")
endif()

file(REAL_PATH "${_default_proto_dir}" _resolved_proto_dir)
set(CHAT_PROTO_DIR "${_resolved_proto_dir}" CACHE PATH "Path to the Buf schema module root containing chat/v1/chat.proto")
set(CHAT_PROTO_FILE "${CHAT_PROTO_DIR}/chat/v1/chat.proto")
if(NOT EXISTS "${CHAT_PROTO_FILE}")
  message(FATAL_ERROR "Protobuf schema not found at ${CHAT_PROTO_FILE}. Set CHAT_PROTO_DIR to the Buf module root.")
endif()

file(REAL_PATH "${CMAKE_CURRENT_SOURCE_DIR}/proto_deps" PROTO_DEPS_DIR)
set(HTTP_PROTO_FILE "${PROTO_DEPS_DIR}/google/api/http.proto")
set(ANNOTATIONS_PROTO_FILE "${PROTO_DEPS_DIR}/google/api/annotations.proto")

find_package(Protobuf CONFIG REQUIRED)
find_package(gRPC CONFIG REQUIRED)
find_package(httplib CONFIG REQUIRED)
find_package(nlohmann_json CONFIG REQUIRED)
find_package(GTest CONFIG REQUIRED)

set(GEN_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(MAKE_DIRECTORY "${GEN_DIR}")

set(GENERATED_PROTO_SRCS
  "${GEN_DIR}/google/api/http.pb.cc"
  "${GEN_DIR}/google/api/annotations.pb.cc"
  "${GEN_DIR}/chat/v1/chat.pb.cc"
  "${GEN_DIR}/chat/v1/chat.grpc.pb.cc"
)
set(GENERATED_PROTO_HDRS
  "${GEN_DIR}/google/api/http.pb.h"
  "${GEN_DIR}/google/api/annotations.pb.h"
  "${GEN_DIR}/chat/v1/chat.pb.h"
  "${GEN_DIR}/chat/v1/chat.grpc.pb.h"
)

add_custom_command(
  OUTPUT ${GENERATED_PROTO_SRCS} ${GENERATED_PROTO_HDRS}
  COMMAND $<TARGET_FILE:protobuf::protoc>
    --proto_path=${CHAT_PROTO_DIR}
    --proto_path=${PROTO_DEPS_DIR}
    --cpp_out=${GEN_DIR}
    --grpc_out=${GEN_DIR}
    --plugin=protoc-gen-grpc=$<TARGET_FILE:gRPC::grpc_cpp_plugin>
    "chat/v1/chat.proto"
  COMMAND $<TARGET_FILE:protobuf::protoc>
    --proto_path=${PROTO_DEPS_DIR}
    --cpp_out=${GEN_DIR}
    "google/api/http.proto"
    "google/api/annotations.proto"
  DEPENDS
    "${CHAT_PROTO_FILE}"
    "${HTTP_PROTO_FILE}"
    "${ANNOTATIONS_PROTO_FILE}"
  COMMENT "Generating C++ Protobuf and gRPC code from chat/v1/chat.proto"
  VERBATIM
)

set(OPENAPI_JSON_FILE "${CHAT_PROTO_DIR}/gen/openapi/rest/chat/v1/chat.openapi.json")
set(OPENAPI_SPEC_CONTENT "")
if(EXISTS "${OPENAPI_JSON_FILE}")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${OPENAPI_JSON_FILE}")
  file(READ "${OPENAPI_JSON_FILE}" OPENAPI_SPEC_CONTENT)
endif()

file(WRITE "${GEN_DIR}/openapi_spec.hpp"
"#pragma once\n\nnamespace chat::generated {\ninline constexpr const char* kSourceOpenApiJson = R\"CHAT_OPENAPI(${OPENAPI_SPEC_CONTENT})CHAT_OPENAPI\";\n}  // namespace chat::generated\n"
)

add_library(chat_backend_lib STATIC
  src/app.cpp
  src/logic.cpp
  src/rest.cpp
  src/service.cpp
  ${GENERATED_PROTO_SRCS}
  ${GENERATED_PROTO_HDRS}
)

target_include_directories(chat_backend_lib
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${GEN_DIR}"
)

target_compile_definitions(chat_backend_lib
  PUBLIC
    $<$<PLATFORM_ID:Windows>:WIN32_LEAN_AND_MEAN NOMINMAX _WIN32_WINNT=0x0A00>
)

target_link_libraries(chat_backend_lib
  PUBLIC
    protobuf::libprotobuf
    gRPC::grpc++
    httplib::httplib
    nlohmann_json::nlohmann_json
)

add_executable(chat-server src/main.cpp)
target_link_libraries(chat-server PRIVATE chat_backend_lib)

enable_testing()

add_executable(chat_tests
  tests/logic_test.cpp
  tests/api_test.cpp
)
target_link_libraries(chat_tests
  PRIVATE
    chat_backend_lib
    GTest::gtest_main
)

add_test(NAME chat_tests COMMAND chat_tests)
