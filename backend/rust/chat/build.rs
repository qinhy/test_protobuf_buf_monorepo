use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use prost::Message as _;

#[derive(Clone, PartialEq, prost::Message)]
struct MiniFileDescriptorSet {
    #[prost(message, repeated, tag = "1")]
    file: Vec<MiniFileDescriptorProto>,
}

#[derive(Clone, PartialEq, prost::Message)]
struct MiniFileDescriptorProto {
    #[prost(string, optional, tag = "1")]
    name: Option<String>,
    #[prost(string, optional, tag = "2")]
    package: Option<String>,
    #[prost(message, repeated, tag = "6")]
    service: Vec<MiniServiceDescriptorProto>,
}

#[derive(Clone, PartialEq, prost::Message)]
struct MiniServiceDescriptorProto {
    #[prost(string, optional, tag = "1")]
    name: Option<String>,
    #[prost(message, repeated, tag = "2")]
    method: Vec<MiniMethodDescriptorProto>,
}

#[derive(Clone, PartialEq, prost::Message)]
struct MiniMethodDescriptorProto {
    #[prost(string, optional, tag = "1")]
    name: Option<String>,
    #[prost(message, optional, tag = "4")]
    options: Option<MiniMethodOptions>,
    #[prost(bool, optional, tag = "6")]
    server_streaming: Option<bool>,
}

#[derive(Clone, PartialEq, prost::Message)]
struct MiniMethodOptions {
    #[prost(message, optional, tag = "72295728")]
    http: Option<MiniHttpRule>,
}

#[derive(Clone, PartialEq, prost::Message)]
struct MiniHttpRule {
    #[prost(string, optional, tag = "2")]
    get: Option<String>,
    #[prost(string, optional, tag = "3")]
    put: Option<String>,
    #[prost(string, optional, tag = "4")]
    post: Option<String>,
    #[prost(string, optional, tag = "5")]
    delete: Option<String>,
    #[prost(string, optional, tag = "6")]
    patch: Option<String>,
}

impl MiniHttpRule {
    fn method_and_path(&self) -> Option<(&'static str, &str)> {
        if let Some(path) = self.post.as_deref() {
            Some(("POST", path))
        } else if let Some(path) = self.get.as_deref() {
            Some(("GET", path))
        } else if let Some(path) = self.put.as_deref() {
            Some(("PUT", path))
        } else if let Some(path) = self.delete.as_deref() {
            Some(("DELETE", path))
        } else if let Some(path) = self.patch.as_deref() {
            Some(("PATCH", path))
        } else {
            None
        }
    }
}

fn resolve_proto_dir(manifest_dir: &Path) -> PathBuf {
    if let Ok(overridden) = env::var("CHAT_PROTO_DIR") {
        let trimmed = overridden.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed);
        }
    }
    manifest_dir.join("../../../proto/chat")
}

fn synthesize_openapi(
    package: &str,
    service: &str,
    say_rpc: &str,
    say_method: &str,
    say_path: &str,
    stream_rpc: &str,
    stream_method: &str,
    stream_path: &str,
) -> String {
    let say_method_lower = say_method.to_ascii_lowercase();
    let stream_method_lower = stream_method.to_ascii_lowercase();
    let say_op_id = format!("{service}_{say_rpc}");
    let stream_op_id = format!("{service}_{stream_rpc}");
    let say_schema = format!("{package}.SayResponse");
    let event_schema = format!("{package}.ChatEvent");
    let event_schema_ref = format!("#/components/schemas/{event_schema}");
    let stream_chunk_schema = format!("StreamResultOf{package}.ChatEvent");
    let spec = serde_json::json!({
        "openapi": "3.1.0",
        "info": {
            "title": "chat",
            "version": "1.0.0"
        },
        "paths": {
            say_path: {
                say_method_lower: {
                    "tags": [service],
                    "summary": "REST is generated from this HTTP annotation, not a handwritten FastAPI route.",
                    "operationId": say_op_id,
                    "requestBody": {
                        "required": true,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "text": {
                                            "type": "string",
                                            "description": "User's message."
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "A successful response.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": format!("#/components/schemas/{say_schema}")
                                    }
                                }
                            }
                        }
                    }
                }
            },
            stream_path: {
                stream_method_lower: {
                    "tags": [service],
                    "summary": "Server-streaming API.",
                    "operationId": stream_op_id,
                    "requestBody": {
                        "required": true,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "text": {
                                            "type": "string",
                                            "description": "User's message."
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Incremental chat events",
                            "content": {
                                "application/x-ndjson": {
                                    "schema": {
                                        "type": "string",
                                        "description": "UTF-8 NDJSON stream, one JSON object per line."
                                    },
                                    "x-ndjson-item-schema": {
                                        "$ref": format!("#/components/schemas/{stream_chunk_schema}")
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                say_schema: {
                    "type": "object",
                    "properties": {
                        "reply": {
                            "type": "string",
                            "description": "Assistant response."
                        }
                    }
                },
                event_schema: {
                    "type": "object",
                    "properties": {
                        "sequence": { "type": "integer" },
                        "start": { "type": "object", "properties": { "messageId": { "type": "string" } } },
                        "delta": { "type": "object", "properties": { "text": { "type": "string" } } },
                        "complete": { "type": "object", "properties": { "reply": { "type": "string" } } },
                        "failure": { "type": "object", "properties": { "code": { "type": "string" }, "message": { "type": "string" } } }
                    }
                },
                stream_chunk_schema: {
                    "type": "object",
                    "properties": {
                        "result": { "$ref": event_schema_ref }
                    }
                }
            }
        }
    });
    serde_json::to_string_pretty(&spec).expect("valid synthesized OpenAPI JSON")
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let manifest_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR")?);
    let out_dir = PathBuf::from(env::var("OUT_DIR")?);
    let proto_dir = resolve_proto_dir(&manifest_dir);
    let proto_deps_dir = manifest_dir.join("proto_deps");
    let chat_proto = proto_dir.join("chat/v1/chat.proto");

    println!("cargo:rerun-if-env-changed=CHAT_PROTO_DIR");
    println!("cargo:rerun-if-changed={}", chat_proto.display());
    println!(
        "cargo:rerun-if-changed={}",
        proto_deps_dir.join("google/api/annotations.proto").display()
    );
    println!(
        "cargo:rerun-if-changed={}",
        proto_deps_dir.join("google/api/http.proto").display()
    );

    if !chat_proto.is_file() {
        return Err(format!(
            "Protobuf schema not found at {}. Set CHAT_PROTO_DIR to the Buf module root.",
            chat_proto.display()
        )
        .into());
    }

    let mut compiler = protox::Compiler::new([&proto_dir, &proto_deps_dir])?;
    compiler
        .include_imports(true)
        .include_source_info(true)
        .open_files(["chat/v1/chat.proto"])?;
    let descriptor_bytes = compiler.encode_file_descriptor_set();
    let descriptor_path = out_dir.join("file_descriptor_set.bin");
    fs::write(&descriptor_path, &descriptor_bytes)?;

    let proto_dir_str = proto_dir.to_str().ok_or("non-UTF-8 CHAT_PROTO_DIR")?;
    let proto_deps_str = proto_deps_dir
        .to_str()
        .ok_or("non-UTF-8 proto_deps path")?;

    let serde_attr =
        "#[derive(serde::Serialize, serde::Deserialize)] #[serde(default, rename_all = \"camelCase\")]";
    tonic_prost_build::configure()
        .file_descriptor_set_path(&descriptor_path)
        .skip_protoc_run()
        .type_attribute(".chat.v1.SayRequest", serde_attr)
        .type_attribute(".chat.v1.SayResponse", serde_attr)
        .type_attribute(".chat.v1.ChatStart", serde_attr)
        .type_attribute(".chat.v1.ChatDelta", serde_attr)
        .type_attribute(".chat.v1.ChatComplete", serde_attr)
        .type_attribute(".chat.v1.ChatFailure", serde_attr)
        .compile_protos(&["chat/v1/chat.proto"], &[proto_dir_str, proto_deps_str])?;

    let mini = MiniFileDescriptorSet::decode(descriptor_bytes.as_slice())?;
    let chat_file = mini
        .file
        .iter()
        .find(|f| f.name.as_deref() == Some("chat/v1/chat.proto"))
        .ok_or("chat/v1/chat.proto missing from compiled FileDescriptorSet")?;
    let package = chat_file
        .package
        .as_deref()
        .ok_or("chat/v1/chat.proto missing package")?;
    let service = chat_file
        .service
        .iter()
        .find(|s| s.name.as_deref() == Some("ChatService"))
        .ok_or("ChatService missing from chat/v1/chat.proto")?;
    let service_name = service.name.as_deref().unwrap_or("ChatService");

    let say_method = service
        .method
        .iter()
        .find(|m| m.name.as_deref() == Some("Say"))
        .ok_or("Say RPC missing from ChatService")?;
    let say_rpc_name = say_method.name.as_deref().unwrap_or("Say");
    let (say_http_method, say_rest_path) = say_method
        .options
        .as_ref()
        .and_then(|o| o.http.as_ref())
        .and_then(|h| h.method_and_path())
        .ok_or("google.api.http annotation missing on ChatService.Say")?;
    let connect_say_path = format!("/{package}.{service_name}/{say_rpc_name}");

    let stream_method = service
        .method
        .iter()
        .find(|m| m.name.as_deref() == Some("StreamSay"))
        .ok_or("StreamSay RPC missing from ChatService")?;
    if stream_method.server_streaming != Some(true) {
        return Err("ChatService.StreamSay must be server-streaming".into());
    }
    let stream_rpc_name = stream_method.name.as_deref().unwrap_or("StreamSay");
    let (stream_http_method, stream_rest_path) = stream_method
        .options
        .as_ref()
        .and_then(|o| o.http.as_ref())
        .and_then(|h| h.method_and_path())
        .ok_or("google.api.http annotation missing on ChatService.StreamSay")?;
    let connect_stream_path = format!("/{package}.{service_name}/{stream_rpc_name}");

    let openapi_file = proto_dir.join("gen/openapi/rest/chat/v1/chat.openapi.json");
    println!("cargo:rerun-if-changed={}", openapi_file.display());
    let openapi_json = openapi_file
        .is_file()
        .then(|| fs::read_to_string(&openapi_file).ok())
        .flatten()
        .filter(|content| {
            serde_json::from_str::<serde_json::Value>(content)
                .ok()
                .and_then(|v| {
                    let paths = v.get("paths")?;
                    let _ = paths.get(say_rest_path)?;
                    let stream_op = paths
                        .get(stream_rest_path)?
                        .get(stream_http_method.to_ascii_lowercase())?;
                    let ndjson = stream_op
                        .get("responses")?
                        .get("200")?
                        .get("content")?
                        .get("application/x-ndjson")?;
                    ndjson.get("x-ndjson-item-schema").map(|_| ())
                })
                .is_some()
        })
        .unwrap_or_else(|| {
            synthesize_openapi(
                package,
                service_name,
                say_rpc_name,
                say_http_method,
                say_rest_path,
                stream_rpc_name,
                stream_http_method,
                stream_rest_path,
            )
        });

    let generated_rest = format!(
        "pub const REST_SAY_METHOD: &str = {say_http_method:?};\n\
         pub const REST_SAY_PATH: &str = {say_rest_path:?};\n\
         pub const CONNECT_SAY_PATH: &str = {connect_say_path:?};\n\
         pub const REST_STREAM_SAY_METHOD: &str = {stream_http_method:?};\n\
         pub const REST_STREAM_SAY_PATH: &str = {stream_rest_path:?};\n\
         pub const CONNECT_STREAM_SAY_PATH: &str = {connect_stream_path:?};\n\
         pub const OPENAPI_JSON: &str = {openapi_json:?};\n"
    );
    fs::write(out_dir.join("rest_generated.rs"), generated_rest)?;

    Ok(())
}
