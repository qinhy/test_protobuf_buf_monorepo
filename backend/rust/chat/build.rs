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

fn synthesize_openapi(package: &str, service: &str, rpc: &str, method: &str, path: &str) -> String {
    let method_lower = method.to_ascii_lowercase();
    let operation_id = format!("{service}_{rpc}");
    let schema_name = format!("{package}.SayResponse");
    let schema_ref = format!("#/components/schemas/{schema_name}");
    let spec = serde_json::json!({
        "openapi": "3.1.0",
        "info": {
            "title": "chat",
            "version": "1.0.0"
        },
        "paths": {
            path: {
                method_lower: {
                    "tags": [service],
                    "summary": "REST is generated from this HTTP annotation.",
                    "operationId": operation_id,
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
                                        "$ref": schema_ref
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
                schema_name: {
                    "type": "object",
                    "properties": {
                        "reply": {
                            "type": "string",
                            "description": "Assistant response."
                        }
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

    tonic_prost_build::configure()
        .file_descriptor_set_path(&descriptor_path)
        .skip_protoc_run()
        .type_attribute(
            ".",
            "#[derive(serde::Serialize, serde::Deserialize)] #[serde(default, rename_all = \"camelCase\")]",
        )
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
    let rpc_name = say_method.name.as_deref().unwrap_or("Say");
    let (http_method, rest_path) = say_method
        .options
        .as_ref()
        .and_then(|o| o.http.as_ref())
        .and_then(|h| h.method_and_path())
        .ok_or("google.api.http annotation missing on ChatService.Say")?;

    let connect_path = format!("/{package}.{service_name}/{rpc_name}");

    let openapi_file = proto_dir.join("gen/openapi/rest/chat/v1/chat.openapi.json");
    println!("cargo:rerun-if-changed={}", openapi_file.display());
    let openapi_json = openapi_file
        .is_file()
        .then(|| fs::read_to_string(&openapi_file).ok())
        .flatten()
        .filter(|content| {
            serde_json::from_str::<serde_json::Value>(content)
                .ok()
                .and_then(|v| v.get("paths")?.get(rest_path).cloned())
                .is_some()
        })
        .unwrap_or_else(|| {
            synthesize_openapi(package, service_name, rpc_name, http_method, rest_path)
        });

    let generated_rest = format!(
        "pub const REST_SAY_METHOD: &str = {http_method:?};\n\
         pub const REST_SAY_PATH: &str = {rest_path:?};\n\
         pub const CONNECT_SAY_PATH: &str = {connect_path:?};\n\
         pub const OPENAPI_JSON: &str = {openapi_json:?};\n"
    );
    fs::write(out_dir.join("rest_generated.rs"), generated_rest)?;

    Ok(())
}
